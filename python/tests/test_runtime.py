"""Runtime installation and diagnosis tests (docs/v2/24 Fase 1).

The seam is the same as the rest of the suite: exit codes, JSON on stdout,
and effects under sandboxed XDG roots. Artifacts are served through file://
URLs so no test ever touches the network.
"""

import json
import stat
from pathlib import Path

import pytest

from archskillkit import runtime
from archskillkit.runtime import (
    CODE_CORRUPTION,
    CODE_HOST_INSUFFICIENT,
    CODE_INCOMPLETE,
    CODE_READY,
    CODE_READY_OFFLINE,
    Paths,
    SetupError,
    run_doctor,
    run_setup,
    setup_lock,
)
from archskillkit.runtime_manifest import (
    ManifestError,
    current_platform,
    load_manifest,
    normalize_machine,
    normalize_system,
)

COMMIT = "a" * 40


def make_binary(tmp_path: Path, artifact_id: str, content: bytes = b"payload") -> dict:
    path = tmp_path / f"{artifact_id}.bin"
    path.write_bytes(content)
    return {
        "id": artifact_id,
        "kind": "binary",
        "version": "1.2.3",
        "url": path.as_uri(),
        "sha256": __import__("hashlib").sha256(content).hexdigest(),
        "size_bytes": len(content),
        "executable": path.name,
        "license": "MIT",
    }


def make_manifest(artifacts: list[dict], **overrides) -> str:
    payload = {
        "schema_version": 1,
        "release": {"version": "0.2.0", "git_tag": "v0.2.0", "commit": COMMIT},
        "platforms": [{
            "os": current_platform()[0],
            "arch": current_platform()[1],
            "artifacts": artifacts,
        }],
        "requirements": {"min_ram_mib": 64, "min_disk_mib": 1,
                         "network": "required-for-setup"},
    }
    payload.update(overrides)
    return json.dumps(payload)


@pytest.fixture()
def paths(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    return Paths.from_env()


class TestManifestParsing:
    def test_valid_manifest_loads(self, tmp_path):
        manifest = load_manifest(make_manifest([make_binary(tmp_path, "ast-grep")]))
        assert manifest.release.version == "0.2.0"
        assert manifest.schema_version == 1

    def test_unsupported_schema_version_rejected(self, tmp_path):
        with pytest.raises(ManifestError, match="schema_version"):
            load_manifest(make_manifest([make_binary(tmp_path, "a")],
                                        schema_version=99))

    def test_malformed_digest_rejected(self, tmp_path):
        artifact = make_binary(tmp_path, "a")
        artifact["sha256"] = "deadbeef"
        with pytest.raises(ManifestError, match="sha256"):
            load_manifest(make_manifest([artifact]))

    def test_duplicate_platform_rejected(self, tmp_path):
        artifact = make_binary(tmp_path, "a")
        platform = json.loads(make_manifest([artifact]))["platforms"][0]
        payload = json.loads(make_manifest([artifact]))
        payload["platforms"].append(platform)
        with pytest.raises(ManifestError, match="duplicate platform"):
            load_manifest(json.dumps(payload))

    def test_duplicate_artifact_id_rejected(self, tmp_path):
        artifact = make_binary(tmp_path, "a")
        payload = json.loads(make_manifest([artifact, artifact]))
        with pytest.raises(ManifestError, match="duplicate artifact id"):
            load_manifest(json.dumps(payload))

    @pytest.mark.parametrize("bad", ["../evil", "/abs/path", "a\\b"])
    def test_unsafe_executable_path_rejected(self, tmp_path, bad):
        artifact = make_binary(tmp_path, "a")
        artifact["executable"] = bad
        with pytest.raises(ManifestError, match="unsafe executable"):
            load_manifest(make_manifest([artifact]))

    def test_attestation_required_without_bundle_rejected(self, tmp_path):
        artifact = make_binary(tmp_path, "a")
        artifact["attestation"] = {"required": True}
        with pytest.raises(ManifestError, match="attestation"):
            load_manifest(make_manifest([artifact]))

    def test_platform_normalization(self):
        assert normalize_machine("AMD64") == "x86_64"
        assert normalize_machine("arm64") == "aarch64"
        assert normalize_system("Linux") == "linux"
        with pytest.raises(ValueError):
            normalize_machine("sparc")


class TestSetup:
    def test_install_activates_runtime_atomically(self, paths, tmp_path):
        manifest = load_manifest(make_manifest([
            make_binary(tmp_path, "ast-grep"),
            make_binary(tmp_path, "node", b"node-binary"),
        ]))
        receipt = run_setup(paths, manifest)
        assert receipt["result"] == "installed"
        key = f"{current_platform()[0]}/{current_platform()[1]}"
        runtime_dir = paths.runtime_dir("0.2.0", key)
        assert (runtime_dir / "installed.json").is_file()
        assert (runtime_dir / "ast-grep.bin").stat().st_mode & stat.S_IXUSR
        assert (runtime_dir / "node.bin").is_file()
        assert paths.receipt_path("0.2.0", key).is_file()
        assert not list(paths.runtimes.glob(".staging-*"))

    def test_setup_is_idempotent(self, paths, tmp_path):
        manifest = load_manifest(make_manifest([make_binary(tmp_path, "a")]))
        assert run_setup(paths, manifest)["result"] == "installed"
        assert run_setup(paths, manifest)["result"] == "already-installed"

    def test_prefetch_fills_cache_without_activation(self, paths, tmp_path):
        manifest = load_manifest(make_manifest([make_binary(tmp_path, "a")]))
        receipt = run_setup(paths, manifest, prefetch=True)
        assert receipt["result"] == "prefetched"
        key = f"{current_platform()[0]}/{current_platform()[1]}"
        assert not paths.runtime_dir("0.2.0", key).exists()
        cached = paths.cache_path(
            json.loads(make_manifest([make_binary(tmp_path, "a")]))
            ["platforms"][0]["artifacts"][0]["sha256"])
        assert cached.is_file()

    def test_offline_fails_with_cache_missing(self, paths, tmp_path):
        manifest = load_manifest(make_manifest([make_binary(tmp_path, "a")]))
        with pytest.raises(SetupError) as excinfo:
            run_setup(paths, manifest, offline=True)
        assert excinfo.value.code == "CACHE_MISSING"
        assert excinfo.value.remedy

    def test_corrupt_cache_fails_offline_and_repairs_online(self, paths, tmp_path):
        artifact = make_binary(tmp_path, "a")
        manifest = load_manifest(make_manifest([artifact]))
        cached = paths.cache_path(artifact["sha256"])
        run_setup(paths, manifest, prefetch=True)
        cached.write_bytes(b"corrupted!")
        with pytest.raises(SetupError) as excinfo:
            run_setup(paths, manifest, offline=True)
        assert excinfo.value.code == "CHECKSUM_MISMATCH"
        receipt = run_setup(paths, manifest)
        assert receipt["result"] == "installed"

    def test_failure_midway_leaves_no_partial_runtime(self, paths, tmp_path,
                                                      monkeypatch):
        artifacts = [make_binary(tmp_path, "first"),
                     make_binary(tmp_path, "second")]
        manifest = load_manifest(make_manifest(artifacts))
        original = runtime._materialize_artifact

        def explode(artifact, staging, cached):
            if artifact.id == "second":
                raise SetupError("CHECKSUM_MISMATCH", "boom", "retry")
            return original(artifact, staging, cached)

        monkeypatch.setattr(runtime, "_materialize_artifact", explode)
        key = f"{current_platform()[0]}/{current_platform()[1]}"
        with pytest.raises(SetupError):
            run_setup(paths, manifest)
        assert not paths.runtime_dir("0.2.0", key).exists()
        assert not list(paths.runtimes.glob(".staging-*"))

    def test_corrupt_runtime_is_reinstalled_by_setup(self, paths, tmp_path):
        artifact = make_binary(tmp_path, "a")
        manifest = load_manifest(make_manifest([artifact]))
        run_setup(paths, manifest)
        key = f"{current_platform()[0]}/{current_platform()[1]}"
        placed = paths.runtime_dir("0.2.0", key) / artifact["executable"]
        placed.write_bytes(b"tampered")
        receipt = run_setup(paths, manifest)
        assert receipt["result"] == "installed"
        assert placed.read_bytes() == b"payload"

    def test_concurrent_setup_is_locked(self, paths, tmp_path):
        manifest = load_manifest(make_manifest([make_binary(tmp_path, "a")]))
        with setup_lock(paths), pytest.raises(SetupError) as excinfo:
            run_setup(paths, manifest)
        assert excinfo.value.code == "SETUP_LOCKED"

    def test_required_attestation_missing_offline(self, paths, tmp_path,
                                                  monkeypatch):
        artifact = make_binary(tmp_path, "a")
        artifact["attestation"] = {"required": True, "bundle": "https://x/bundle"}
        manifest = load_manifest(make_manifest([artifact]))
        monkeypatch.setattr(runtime, "_ensure_attestation",
                            lambda *a, **k: None)
        run_setup(paths, manifest, prefetch=True)
        monkeypatch.undo()
        with pytest.raises(SetupError) as excinfo:
            run_setup(paths, manifest, offline=True)
        assert excinfo.value.code == "ATTESTATION_MISSING"


class TestDoctor:
    def test_no_manifest_is_incomplete(self, paths):
        diagnosis, exit_code = run_doctor(paths, None)
        assert diagnosis["status"] == CODE_INCOMPLETE
        assert exit_code == runtime.EXIT_INCOMPLETE

    def test_fresh_cache_is_incomplete(self, paths, tmp_path):
        manifest = load_manifest(make_manifest([make_binary(tmp_path, "a")]))
        diagnosis, exit_code = run_doctor(paths, manifest)
        assert diagnosis["status"] == CODE_INCOMPLETE
        assert exit_code == runtime.EXIT_INCOMPLETE

    def test_prefetched_cache_is_ready_offline(self, paths, tmp_path):
        manifest = load_manifest(make_manifest([make_binary(tmp_path, "a")]))
        run_setup(paths, manifest, prefetch=True)
        diagnosis, exit_code = run_doctor(paths, manifest)
        assert diagnosis["status"] == CODE_READY_OFFLINE
        assert exit_code == 0

    def test_installed_runtime_is_ready(self, paths, tmp_path):
        manifest = load_manifest(make_manifest([make_binary(tmp_path, "a")]))
        run_setup(paths, manifest)
        diagnosis, exit_code = run_doctor(paths, manifest)
        assert diagnosis["status"] == CODE_READY
        assert exit_code == 0

    def test_corrupt_runtime_is_corruption(self, paths, tmp_path):
        artifact = make_binary(tmp_path, "a")
        manifest = load_manifest(make_manifest([artifact]))
        run_setup(paths, manifest)
        key = f"{current_platform()[0]}/{current_platform()[1]}"
        placed = paths.runtime_dir("0.2.0", key) / artifact["executable"]
        placed.write_bytes(b"tampered")
        diagnosis, exit_code = run_doctor(paths, manifest)
        assert diagnosis["status"] == CODE_CORRUPTION
        assert exit_code == runtime.EXIT_CORRUPTION

    def test_low_ram_is_host_insufficient(self, paths, tmp_path, monkeypatch):
        manifest = load_manifest(make_manifest([make_binary(tmp_path, "a")]))
        run_setup(paths, manifest)
        monkeypatch.setattr(runtime, "available_memory_mib", lambda: 1)
        diagnosis, exit_code = run_doctor(paths, manifest)
        assert diagnosis["status"] == CODE_HOST_INSUFFICIENT
        assert exit_code == runtime.EXIT_HOST
        codes = {f["code"] for f in diagnosis["findings"]}
        assert "HOST_RAM_INSUFFICIENT" in codes

    def test_unsupported_platform_is_host_insufficient(self, paths, tmp_path):
        other = "darwin" if current_platform()[0] == "linux" else "linux"
        manifest = load_manifest(make_manifest([make_binary(tmp_path, "a")]))
        payload = json.loads(make_manifest([make_binary(tmp_path, "a")]))
        payload["platforms"][0]["os"] = other
        manifest = load_manifest(json.dumps(payload))
        diagnosis, _exit_code = run_doctor(paths, manifest)
        assert diagnosis["status"] == CODE_HOST_INSUFFICIENT
        assert diagnosis["findings"][0]["code"] == "PLATFORM_UNSUPPORTED"

    def test_doctor_never_writes(self, paths, tmp_path):
        manifest = load_manifest(make_manifest([make_binary(tmp_path, "a")]))
        before = sorted(str(p) for p in paths.state.rglob("*")) \
            if paths.state.exists() else []
        run_doctor(paths, manifest)
        after = sorted(str(p) for p in paths.state.rglob("*")) \
            if paths.state.exists() else []
        assert before == after


class TestPreflight:
    def test_disk_pressure_blocks_before_download(self, paths, tmp_path,
                                                  monkeypatch):
        manifest = load_manifest(make_manifest([make_binary(tmp_path, "a")]))
        monkeypatch.setattr(runtime, "free_disk_mib", lambda _: 0)
        with pytest.raises(SetupError) as excinfo:
            run_setup(paths, manifest)
        assert excinfo.value.code == "HOST_DISK_INSUFFICIENT"
        key = f"{current_platform()[0]}/{current_platform()[1]}"
        assert not paths.runtime_dir("0.2.0", key).exists()

    def test_low_ram_blocks_before_download(self, paths, tmp_path, monkeypatch):
        manifest = load_manifest(make_manifest([make_binary(tmp_path, "a")]))
        monkeypatch.setattr(runtime, "available_memory_mib", lambda: 1)
        with pytest.raises(SetupError) as excinfo:
            run_setup(paths, manifest)
        assert excinfo.value.code == "HOST_RAM_INSUFFICIENT"


class TestSigstoreVerification:
    """V2.3 follow-up: required attestations are cryptographically
    verified (sigstore) — never silently passed. Prefetch already runs
    verification, so fakes must be active before it."""

    def _contract_manifest(self, tmp_path):
        artifact = make_binary(tmp_path, "a")
        artifact["attestation"] = {"required": True,
                                   "repository": "rubentxu/fixture"}
        return load_manifest(make_manifest([artifact])), artifact

    def _fake_fetch(self, monkeypatch):
        def fake_fetch(repository, digest, dest):
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text('{"mediaType": "fake-bundle"}')

        monkeypatch.setattr(runtime, "_fetch_attestation_bundle", fake_fetch)

    def _fake_sigstore(self, monkeypatch, holder):
        import subprocess as subprocess_module

        def fake_run(cmd, **kwargs):
            class R:
                returncode = holder["rc"]
                stderr = "boom" if holder["rc"] else ""
                stdout = ""
            return R()

        monkeypatch.setattr(subprocess_module, "run", fake_run)

    def test_sigstore_failure_hard_fails(self, paths, tmp_path, monkeypatch):
        self._fake_fetch(monkeypatch)
        holder = {"rc": 0}
        self._fake_sigstore(monkeypatch, holder)
        manifest, _ = self._contract_manifest(tmp_path)
        run_setup(paths, manifest, prefetch=True)
        holder["rc"] = 1
        with pytest.raises(SetupError) as excinfo:
            run_setup(paths, manifest)
        assert excinfo.value.code == "ATTESTATION_INVALID"

    def test_sigstore_missing_hard_fails(self, paths, tmp_path, monkeypatch):
        import subprocess as subprocess_module

        self._fake_fetch(monkeypatch)
        holder = {"rc": 0}
        self._fake_sigstore(monkeypatch, holder)
        manifest, _ = self._contract_manifest(tmp_path)
        run_setup(paths, manifest, prefetch=True)

        def raise_fnf(cmd, **kwargs):
            raise FileNotFoundError("sigstore")

        monkeypatch.setattr(subprocess_module, "run", raise_fnf)
        with pytest.raises(SetupError) as excinfo:
            run_setup(paths, manifest)
        assert excinfo.value.code == "ATTESTATION_INVALID"
        assert "attestation" in excinfo.value.remedy

    def test_verified_attestation_allows_install(self, paths, tmp_path,
                                                 monkeypatch):
        self._fake_fetch(monkeypatch)
        holder = {"rc": 0}
        self._fake_sigstore(monkeypatch, holder)
        manifest, _ = self._contract_manifest(tmp_path)
        run_setup(paths, manifest, prefetch=True)
        receipt = run_setup(paths, manifest)
        assert receipt["result"] == "installed"
        key = f"{current_platform()[0]}/{current_platform()[1]}"
        assert paths.runtime_dir("0.2.0", key).exists()
