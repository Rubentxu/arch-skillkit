"""Runtime installation and verification (docs/v2/24-distribution-and-installation, Fase 1).

`setup` owns the third-party runtime: preflight, digest-addressed cache,
transactional staging with atomic activation, and receipts. It may repair:
a corrupt cache entry is re-downloaded, a corrupt runtime is reinstalled.
`doctor` never downloads nor repairs: it reports a JSON diagnosis with
distinct statuses for incomplete, corruption and host-insufficient.

Doctor exit codes: 0 ready/ready-offline, 1 incomplete, 2 corruption,
3 host-insufficient. Setup exit codes: 0 ok, 2 hard precondition failure
(the stable finding code is printed as JSON to stdout and the message to
stderr).
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import shutil
import socket
import stat
import sys
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from archskillkit.ids import arch_cache_root, arch_data_root, arch_state_root
from archskillkit.runtime_manifest import (
    Artifact,
    ManifestError,
    RuntimeManifest,
    current_platform,
)

CHUNK = 1 << 20
MIB = 1 << 20
DISK_MARGIN_MIB = 64

CODE_READY = "ready"
CODE_READY_OFFLINE = "ready-offline"
CODE_INCOMPLETE = "incomplete"
CODE_CORRUPTION = "corruption"
CODE_HOST_INSUFFICIENT = "host-insufficient"

EXIT_INCOMPLETE = 1
EXIT_CORRUPTION = 2
EXIT_HOST = 3

_CORRUPTION_CODES = {"CHECKSUM_MISMATCH", "ATTESTATION_MISSING",
                     "ATTESTATION_INVALID"}
_HOST_CODES = {"PLATFORM_UNSUPPORTED", "RUNTIME_INCOMPATIBLE",
               "HOST_RAM_INSUFFICIENT", "HOST_DISK_INSUFFICIENT",
               "HOST_CPU_INSUFFICIENT"}


class SetupError(Exception):
    """A hard, stable, actionable setup failure."""

    def __init__(self, code: str, message: str, remedy: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.remedy = remedy

    def as_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "remedy": self.remedy}


@dataclass
class Finding:
    code: str
    message: str
    remedy: str = ""

    def as_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "remedy": self.remedy}


@dataclass
class Paths:
    data: Path
    cache: Path
    state: Path

    @classmethod
    def from_env(cls) -> "Paths":
        return cls(
            data=arch_data_root(),
            cache=arch_cache_root() / "downloads" / "sha256",
            state=arch_state_root(),
        )

    @property
    def runtimes(self) -> Path:
        return self.data / "runtimes"

    def runtime_dir(self, version: str, platform_key: str) -> Path:
        return self.runtimes / version / platform_key

    def cache_path(self, digest: str) -> Path:
        return self.cache / digest

    @property
    def lock_path(self) -> Path:
        return self.state / "locks" / "setup.lock"

    def receipt_path(self, version: str, platform_key: str) -> Path:
        return self.state / "receipts" / f"setup-{version}-{platform_key}.json"

    def stored_manifest_path(self, version: str) -> Path:
        return self.state / "manifests" / f"v{version}.manifest.json"


def current_platform_key() -> str:
    os_name, arch = current_platform()
    return f"{os_name}/{arch}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def available_memory_mib() -> int | None:
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) // 1024
    except OSError:
        pass
    with contextlib.suppress(OSError, ValueError, AttributeError):
        return (os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_AVPHYS_PAGES")) // MIB
    return None


def free_disk_mib(path: Path) -> int | None:
    with contextlib.suppress(OSError):
        return shutil.disk_usage(path).free // MIB
    return None


def recommended_threads(cores: int | None) -> int:
    return max(1, min(4, (cores or 1) - 1))


def network_available(url: str, timeout: float = 5.0) -> bool:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme in ("file", ""):
        return True
    host = parsed.hostname
    if not host:
        return False
    try:
        with socket.create_connection((host, 443), timeout=timeout):
            return True
    except OSError:
        return False


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        url, headers={"User-Agent": "archskillkit-setup"})
    tmp = dest.with_name(f".{dest.name}.{uuid.uuid4().hex}.part")
    try:
        with urllib.request.urlopen(request) as response, tmp.open("wb") as out:
            while chunk := response.read(CHUNK):
                out.write(chunk)
        os.replace(tmp, dest)
    except (urllib.error.URLError, OSError) as exc:
        raise SetupError(
            "NETWORK_UNAVAILABLE",
            f"download failed for {url}: {exc}",
            "check connectivity and retry; the cache stays consistent") from exc
    finally:
        tmp.unlink(missing_ok=True)


def ensure_cached(paths: Paths, artifact: Artifact, *, offline: bool) -> Path:
    """Return a verified cache entry, repairing a corrupt one when online."""
    cached = paths.cache_path(artifact.sha256)
    if cached.is_file():
        if _cache_entry_ok(cached, artifact):
            return cached
        if offline:
            raise SetupError(
                "CHECKSUM_MISMATCH",
                f"cache entry for {artifact.id} is corrupt: {cached}",
                "clear the downloads cache and re-run setup --prefetch on a"
                " connected host")
        cached.unlink()
    if offline:
        raise SetupError(
            "CACHE_MISSING",
            f"artifact {artifact.id} ({artifact.version}) is not in the"
            " offline cache",
            "populate the cache with setup --prefetch on a connected host,"
            " or re-run setup without --offline")
    if not network_available(artifact.url):
        raise SetupError(
            "NETWORK_UNAVAILABLE",
            f"cannot reach {urllib.parse.urlparse(artifact.url).hostname}"
            f" to fetch {artifact.id}",
            "check connectivity or pre-populate the cache with"
            " setup --prefetch")
    download(artifact.url, cached)
    if cached.stat().st_size != artifact.size_bytes:
        raise SetupError(
            "CHECKSUM_MISMATCH",
            f"downloaded {artifact.id} has unexpected size"
            f" ({cached.stat().st_size} != {artifact.size_bytes})",
            "retry setup; the manifest digest must match for the run to"
            " proceed")
    actual = sha256_file(cached)
    if actual != artifact.sha256:
        raise SetupError(
            "CHECKSUM_MISMATCH",
            f"downloaded {artifact.id} digest mismatch ({actual} !="
            f" {artifact.sha256})",
            "retry setup; if it persists, distrust the manifest and re-fetch"
            " it")
    return cached


def _cache_entry_ok(cached: Path, artifact: Artifact) -> bool:
    try:
        return (cached.stat().st_size == artifact.size_bytes
                and sha256_file(cached) == artifact.sha256)
    except OSError:
        return False


def _archive_format(url: str) -> str | None:
    path = urllib.parse.urlparse(url).path.lower()
    if path.endswith(".zip"):
        return "zip"
    if path.endswith((".tar.gz", ".tgz")):
        return "tar.gz"
    return None


def _collect_archive(
    archive: Path, target: Path, *, fmt: str
) -> None:
    target.mkdir(parents=True, exist_ok=True)
    if fmt == "zip":
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(target, members=_safe_zip_members(zf.namelist()))
    else:
        # PEP 706 "data" filter: rejects absolute paths, parent traversal,
        # special files and escaping links. Hand-rolled member filters break
        # hardlink members produced by GNU tar --dereference.
        with tarfile.open(archive, "r:gz") as tf:
            tf.extractall(target, filter="data")
    _strip_single_top_dir(target)


def _safe_zip_members(names: list[str]) -> list[str]:
    safe = []
    for name in names:
        parts = Path(name).parts
        if name.startswith("/") or ".." in parts or name.endswith("/"):
            continue
        safe.append(name)
    return safe


def _strip_single_top_dir(target: Path) -> None:
    entries = list(target.iterdir())
    if len(entries) != 1 or not entries[0].is_dir():
        return
    top = entries[0]
    for child in top.iterdir():
        os.replace(child, target / child.name)
    top.rmdir()


def _merge_dir(source: Path, target: Path) -> None:
    for child in sorted(source.rglob("*")):
        destination = target / child.relative_to(source)
        if child.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(child, destination)


def _materialize_artifact(
    artifact: Artifact, staging: Path, cached: Path
) -> dict[str, str]:
    """Lay the artifact out inside staging; return {relpath: sha256} evidence.

    The cache is content-addressed, so the artifact format is decided by the
    manifest URL, never by the cached file name.
    """
    fmt = _archive_format(artifact.url)
    recorded: dict[str, str] = {}
    if artifact.kind == "binary":
        if fmt is None:
            if not artifact.executable:
                raise SetupError(
                    "RUNTIME_INCOMPATIBLE",
                    f"plain binary artifact {artifact.id} must declare its"
                    " executable path",
                    "set 'executable' in the manifest artifact")
            placed = staging / artifact.executable
            placed.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(cached, placed)
            placed.chmod(placed.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP
                         | stat.S_IXOTH)
            recorded[artifact.executable] = sha256_file(placed)
            return recorded
        work = staging / f".unpack-{artifact.id}"
        _collect_archive(cached, work, fmt=fmt)
        if artifact.executable:
            unpacked = work / artifact.executable
            if not unpacked.is_file():
                raise SetupError(
                    "RUNTIME_INCOMPATIBLE",
                    f"artifact {artifact.id} does not contain expected"
                    f" executable {artifact.executable}",
                    "the manifest layout must match the published artifact")
            unpacked.chmod(unpacked.stat().st_mode | stat.S_IXUSR
                           | stat.S_IXGRP | stat.S_IXOTH)
            recorded[artifact.executable] = sha256_file(unpacked)
        _merge_dir(work, staging)
        shutil.rmtree(work, ignore_errors=True)
    elif artifact.kind == "npm-bundle":
        if fmt != "tar.gz":
            raise SetupError(
                "RUNTIME_INCOMPATIBLE",
                f"npm bundle {artifact.id} must be a .tar.gz/.tgz archive",
                "publish the release bundle as a tarball")
        work = staging / f".unpack-{artifact.id}"
        _collect_archive(cached, work, fmt=fmt)
        target = staging / "likec4"
        if target.exists():
            shutil.rmtree(target)
        os.replace(work, target)
        marker = target / "package.json"
        if not marker.is_file():
            raise SetupError(
                "RUNTIME_INCOMPATIBLE",
                f"npm bundle {artifact.id} has no package.json at its root",
                "the release bundle must contain package.json at the top"
                " level")
        recorded["likec4/package.json"] = sha256_file(marker)
    elif artifact.kind == "wheelhouse":
        if fmt != "tar.gz":
            raise SetupError(
                "RUNTIME_INCOMPATIBLE",
                f"wheelhouse {artifact.id} must be a .tar.gz archive",
                "publish the wheelhouse as a tarball")
        work = staging / "wheelhouse"
        _collect_archive(cached, work, fmt=fmt)
        wheels = sorted(work.glob("*.whl"))
        if not wheels:
            raise SetupError(
                "RUNTIME_INCOMPATIBLE",
                f"wheelhouse {artifact.id} contains no wheels",
                "the release wheelhouse must contain *.whl files at its root")
        for wheel in wheels:
            recorded[f"wheelhouse/{wheel.name}"] = sha256_file(wheel)
        if artifact.install:
            _build_venv(staging / "semgrep-venv", work, artifact.install)
    return recorded


def _build_venv(venv_dir: Path, wheelhouse: Path, packages: list[str]) -> None:
    import subprocess
    import venv as venv_module

    builder = venv_module.EnvBuilder(with_pip=True, clear=True)
    try:
        builder.create(venv_dir)
    except Exception as exc:
        raise SetupError(
            "RUNTIME_INCOMPATIBLE",
            f"could not create the isolated Python environment: {exc}",
            "ensure python3-venv support is available on this host") from exc
    python_bin = venv_dir / "bin" / "python"
    if not python_bin.is_file():
        raise SetupError(
            "RUNTIME_INCOMPATIBLE",
            "could not create the isolated Python environment for semgrep",
            "ensure python3-venv support is available on this host")
    result = subprocess.run(
        [str(python_bin), "-m", "pip", "install", "--no-index",
         "--no-cache-dir", "--find-links", str(wheelhouse), *packages],
        check=False, capture_output=True)
    if result.returncode != 0:
        shutil.rmtree(venv_dir, ignore_errors=True)
        raise SetupError(
            "RUNTIME_INCOMPATIBLE",
            f"offline pip install failed for {', '.join(packages)}:",
            f"{result.stderr.decode(errors='replace')[-400:]}",
            )


def _fix_venv_shebangs(runtime_dir: Path, staging: Path) -> None:
    """Rewrite console-script shebangs that baked the staging path at venv
    creation time; the atomic rename made them stale."""
    bin_dir = runtime_dir / "semgrep-venv" / "bin"
    if not bin_dir.is_dir():
        return
    old = str(staging).encode()
    new = str(runtime_dir).encode()
    for script in bin_dir.iterdir():
        if not script.is_file():
            continue
        with script.open("rb") as handle:
            head = handle.readline()
        if head.startswith(b"#!") and old in head:
            body = script.read_bytes()
            script.write_bytes(body.replace(head, head.replace(old, new), 1))


def _runtime_evidence(runtime_dir: Path) -> dict | None:
    marker = runtime_dir / "installed.json"
    if not marker.is_file():
        return None
    try:
        return json.loads(marker.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def is_runtime_complete(
    paths: Paths, manifest: RuntimeManifest, platform_key: str
) -> tuple[bool, list[Finding], list[str]]:
    """(installed_ok, corruption_findings, missing_artifact_ids)."""
    platform_entry = manifest.platform_for(*platform_key.split("/"))
    if platform_entry is None:
        return False, [], []
    runtime_dir = paths.runtime_dir(manifest.release.version, platform_key)
    evidence = _runtime_evidence(runtime_dir)
    if evidence is None:
        return False, [], [a.id for a in platform_entry.artifacts]
    findings: list[Finding] = []
    missing: list[str] = []
    recorded: dict[str, dict[str, str]] = evidence.get("artifacts", {})
    for artifact in platform_entry.artifacts:
        files = recorded.get(artifact.id)
        if not files:
            missing.append(artifact.id)
            continue
        for rel, digest in files.items():
            placed = runtime_dir / rel
            if not placed.is_file() or sha256_file(placed) != digest:
                findings.append(Finding(
                    "CHECKSUM_MISMATCH",
                    f"installed artifact {artifact.id} is corrupt: {rel}",
                    "re-run setup to reinstall the runtime"))
    complete = bool(recorded) and not missing and not findings
    return complete, findings, missing


def cache_state(
    paths: Paths, manifest: RuntimeManifest, platform_key: str
) -> tuple[bool, list[str], list[Finding]]:
    """(cache_complete, missing_artifact_ids, corruption_findings)."""
    platform_entry = manifest.platform_for(*platform_key.split("/"))
    if platform_entry is None:
        return False, [], []
    findings: list[Finding] = []
    missing: list[str] = []
    for artifact in platform_entry.artifacts:
        cached = paths.cache_path(artifact.sha256)
        if not cached.is_file():
            missing.append(artifact.id)
        elif sha256_file(cached) != artifact.sha256:
            findings.append(Finding(
                "CHECKSUM_MISMATCH",
                f"cache entry for {artifact.id} does not match the manifest"
                " digest",
                f"delete {cached} and re-run setup"))
    return (not missing and not findings), missing, findings


def preflight(
    paths: Paths,
    manifest: RuntimeManifest,
    *,
    offline: bool,
) -> tuple[list[Finding], list[Finding]]:
    """Hard failures and warnings, measured before anything is mutated."""
    hard: list[Finding] = []
    warnings: list[Finding] = []
    key = current_platform_key()
    platform_entry = manifest.platform_for(*key.split("/"))
    if platform_entry is None:
        hard.append(Finding(
            "PLATFORM_UNSUPPORTED",
            f"no runtime artifacts for {key} in manifest v"
            f"{manifest.release.version}",
            "check the supported platforms in the release manifest"))
        return hard, warnings
    if sys.version_info < (3, 11):
        hard.append(Finding(
            "RUNTIME_INCOMPATIBLE",
            f"python {sys.version_info.major}.{sys.version_info.minor} is"
            " older than the required 3.11",
            "use python >= 3.11 (uv can install a managed interpreter)"))
        return hard, warnings

    cores = os.cpu_count()
    if not cores:
        hard.append(Finding(
            "HOST_CPU_INSUFFICIENT",
            "could not determine any available CPU",
            "run on a host with at least one core"))
    else:
        warnings.append(Finding(
            "HOST_CPU_DEGRADED",
            f"{cores} cores detected; scanners will run with"
            f" {recommended_threads(cores)} thread(s)",
            "override only with an explicit, evidenced flag"))

    ram = available_memory_mib()
    if ram is not None and ram < manifest.requirements.min_ram_mib:
        hard.append(Finding(
            "HOST_RAM_INSUFFICIENT",
            f"{ram} MiB available < {manifest.requirements.min_ram_mib} MiB"
            " required",
            "free memory or use a larger host; nothing was downloaded"))

    _, corrupt_runtime, _ = is_runtime_complete(paths, manifest, key)
    _, cache_missing, cache_corrupt = cache_state(paths, manifest, key)
    needs_install = bool(cache_missing or corrupt_runtime)
    if offline and cache_corrupt:
        hard.extend(cache_corrupt)
    disk_free = free_disk_mib(paths.runtimes if paths.runtimes.exists()
                              else paths.data)
    if needs_install:
        sizes = {a.id: a.size_bytes for a in platform_entry.artifacts}
        missing_bytes = sum(sizes[i] for i in cache_missing)
        needed_mib = max((missing_bytes // MIB) + DISK_MARGIN_MIB,
                         manifest.requirements.min_disk_mib)
        if disk_free is not None and disk_free < needed_mib:
            hard.append(Finding(
                "HOST_DISK_INSUFFICIENT",
                f"{disk_free} MiB free < {needed_mib} MiB needed"
                " (artifacts + staging + margin)",
                "free disk space; nothing was downloaded or installed"))
        if cache_missing and not offline:
            if not network_available(platform_entry.artifacts[0].url):
                hard.append(Finding(
                    "NETWORK_UNAVAILABLE",
                    "network is unreachable and the cache is incomplete",
                    "restore connectivity or pre-populate the cache with"
                    " setup --prefetch"))
    return hard, warnings


@contextlib.contextmanager
def setup_lock(paths: Paths):
    paths.lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = paths.lock_path.open("w")
    try:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise SetupError(
                "SETUP_LOCKED",
                "another setup transaction holds the runtime lock",
                f"wait for it to finish; lock file: {paths.lock_path}") from exc
        yield
    finally:
        with contextlib.suppress(OSError):
            fcntl.flock(handle, fcntl.LOCK_UN)
        handle.close()


def load_manifest_for_setup(
    paths: Paths, manifest_source: str | None, *, offline: bool
) -> tuple[RuntimeManifest, str | None]:
    """Resolve the manifest: --manifest source, stored copy, then release URL."""
    from archskillkit import __version__

    if manifest_source:
        manifest = read_manifest_source(manifest_source)
        stored = paths.stored_manifest_path(manifest.release.version)
        stored.parent.mkdir(parents=True, exist_ok=True)
        stored.write_text(json.dumps(manifest.model_dump(), indent=2))
        return manifest, manifest_source
    stored = paths.stored_manifest_path(__version__)
    if stored.is_file():
        try:
            return read_manifest_source(str(stored)), str(stored)
        except ManifestError:
            pass
    if offline:
        raise SetupError(
            "CACHE_MISSING",
            "offline mode has no stored runtime manifest",
            "run setup once with --manifest or connectivity, or pass"
            " --manifest explicitly")
    url = ("https://github.com/Rubentxu/arch-skillkit/releases/download/"
           f"v{__version__}/archskillkit-runtime-v{__version__}.manifest.json")
    if not network_available(url):
        raise SetupError(
            "NETWORK_UNAVAILABLE",
            f"no stored manifest and cannot reach {url}",
            "pass --manifest with a local copy, or restore connectivity")
    tmp = Path(tempfile.mkstemp(suffix=".json")[1])
    try:
        download(url, tmp)
        manifest = read_manifest_source(str(tmp))
        stored = paths.stored_manifest_path(__version__)
        stored.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(tmp, stored)
        return manifest, url
    finally:
        tmp.unlink(missing_ok=True)


def read_manifest_source(source: str) -> RuntimeManifest:
    from urllib.request import url2pathname

    from archskillkit.runtime_manifest import load_manifest

    parsed = urllib.parse.urlparse(source)
    if parsed.scheme in ("http", "https"):
        with urllib.request.urlopen(source) as response:
            return load_manifest(response.read().decode())
    if parsed.scheme == "file":
        return load_manifest(Path(url2pathname(parsed.path)).read_text())
    return load_manifest(Path(source).read_text())


def run_setup(
    paths: Paths,
    manifest: RuntimeManifest,
    *,
    offline: bool = False,
    prefetch: bool = False,
) -> dict:
    """Preflight → cache → staging → atomic activation → receipt."""
    key = current_platform_key()
    hard, warnings = preflight(paths, manifest, offline=offline)
    if hard:
        first = hard[0]
        raise SetupError(first.code, first.message, first.remedy)
    platform_entry = manifest.platform_for(*key.split("/"))
    assert platform_entry is not None

    with setup_lock(paths):
        installed, corrupt_runtime, _ = is_runtime_complete(
            paths, manifest, key)
        if installed and not corrupt_runtime:
            receipt = _write_receipt(paths, manifest, key, result="installed",
                                     already=True)
            return _with_warnings(receipt, warnings)

        for artifact in platform_entry.artifacts:
            ensure_cached(paths, artifact, offline=offline)
            _ensure_attestation(paths, artifact, offline=offline)
        if prefetch:
            receipt = _write_receipt(paths, manifest, key, result="prefetched",
                                     already=False)
            return _with_warnings(receipt, warnings)

        final = paths.runtime_dir(manifest.release.version, key)
        staging = paths.runtimes / f".staging-{uuid.uuid4().hex}"
        activated = False
        try:
            paths.runtimes.mkdir(parents=True, exist_ok=True)
            staging.mkdir(parents=True)
            evidence: dict[str, dict[str, str]] = {}
            for artifact in platform_entry.artifacts:
                cached = paths.cache_path(artifact.sha256)
                evidence[artifact.id] = _materialize_artifact(
                    artifact, staging, cached)
            if final.is_dir():
                shutil.rmtree(final)
            elif final.exists():
                final.unlink()
            final.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staging, final)
            activated = True
            _fix_venv_shebangs(final, staging)
            (final / "installed.json").write_text(json.dumps({
                "version": manifest.release.version,
                "platform": key,
                "release": manifest.release.model_dump(),
                "artifacts": evidence,
                "installed_at": datetime.now(UTC).isoformat(timespec="seconds"),
            }, indent=2))
        except SetupError:
            shutil.rmtree(final if activated else staging, ignore_errors=True)
            raise
        except (OSError, tarfile.TarError, zipfile.BadZipFile) as exc:
            shutil.rmtree(final if activated else staging, ignore_errors=True)
            raise SetupError(
                "RUNTIME_INCOMPATIBLE",
                f"staging failed: {exc}",
                "retry setup; a partial runtime is never activated") from exc
        receipt = _write_receipt(paths, manifest, key, result="installed",
                                 already=False)
        return _with_warnings(receipt, warnings)


def _ensure_attestation(
    paths: Paths, artifact: Artifact, *, offline: bool
) -> None:
    """Policy v1: a required bundle must be present; Sigstore verification is
    Fase 0 work. Required-but-absent is a hard failure, never a silent pass."""
    if not artifact.attestation.required or not artifact.attestation.bundle:
        return
    bundle_url = artifact.attestation.bundle
    key = (artifact.attestation.subject_sha256
           or hashlib.sha256(bundle_url.encode()).hexdigest())
    target = paths.cache / "attestations" / key
    if target.is_file():
        return
    if offline:
        raise SetupError(
            "ATTESTATION_MISSING",
            f"attestation bundle for {artifact.id} is required and not cached",
            f"prefetch {bundle_url} or ship it with the air-gapped bundle")
    download(bundle_url, target)


def _write_receipt(
    paths: Paths,
    manifest: RuntimeManifest,
    platform_key: str,
    *,
    result: str,
    already: bool,
) -> dict:
    receipt = {
        "schema_version": 1,
        "command": "setup",
        "release": manifest.release.model_dump(),
        "platform": platform_key,
        "result": "already-installed" if already else result,
        "requirements": manifest.requirements.model_dump(),
        "finished_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    path = paths.receipt_path(manifest.release.version, platform_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, indent=2))
    return receipt


def _with_warnings(receipt: dict, warnings: list[Finding]) -> dict:
    if warnings:
        receipt["warnings"] = [w.as_dict() for w in warnings]
    return receipt


def run_doctor(paths: Paths, manifest: RuntimeManifest | None) -> tuple[dict, int]:
    """Read-only diagnosis. Never downloads, never repairs, never mutates."""
    checks: list[dict] = []
    findings: list[Finding] = []
    key = current_platform_key()

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "status": "ok" if ok else "fail",
                       "detail": detail})

    if manifest is None:
        manifest = _stored_manifest(paths)
        if manifest is None:
            add("manifest", False, "no runtime manifest known (run setup first)")
            findings.append(Finding(
                "CACHE_MISSING",
                "no runtime manifest available for diagnosis",
                "run: archskillkit setup --manifest <path-or-url>"))

    installed = False
    cache_complete = False
    platform_ok = False

    if manifest is not None:
        version = manifest.release.version
        add("manifest", True, f"v{version}, schema {manifest.schema_version}")
        platform_entry = manifest.platform_for(*key.split("/"))
        platform_ok = platform_entry is not None
        add("platform", platform_ok,
            key if platform_ok else f"{key} not supported by manifest v{version}")
        if platform_entry is None:
            findings.append(Finding(
                "PLATFORM_UNSUPPORTED",
                f"platform {key} is not in manifest v{version}",
                "use a supported platform"))
        else:
            installed, install_findings, missing = is_runtime_complete(
                paths, manifest, key)
            findings.extend(install_findings)
            add("runtime", installed,
                "installed and verified" if installed else
                (f"corrupt: {len(install_findings)} finding(s)"
                 if install_findings else
                 f"not installed (missing: {', '.join(missing)})"))
            if not installed:
                cache_complete, cache_missing, cache_findings = cache_state(
                    paths, manifest, key)
                findings.extend(cache_findings)
                add("cache", cache_complete,
                    "complete for offline setup" if cache_complete else
                    f"missing: {', '.join(cache_missing)}")

        ram = available_memory_mib()
        ram_ok = ram is None or ram >= manifest.requirements.min_ram_mib
        add("ram", ram_ok,
            f"{ram if ram is not None else '?'} MiB available /"
            f" {manifest.requirements.min_ram_mib} MiB required")
        if not ram_ok:
            findings.append(Finding(
                "HOST_RAM_INSUFFICIENT",
                f"{ram} MiB available < {manifest.requirements.min_ram_mib} MiB",
                "free memory or use a larger host"))
        free = free_disk_mib(paths.data)
        disk_ok = free is None or free >= manifest.requirements.min_disk_mib
        add("disk", disk_ok,
            f"{free if free is not None else '?'} MiB free /"
            f" {manifest.requirements.min_disk_mib} MiB required")
        if not disk_ok:
            findings.append(Finding(
                "HOST_DISK_INSUFFICIENT",
                f"{free} MiB free < {manifest.requirements.min_disk_mib} MiB",
                "free disk space"))
        add("cpu", True,
            f"{os.cpu_count() or '?'} cores; scanner budget:"
            f" {recommended_threads(os.cpu_count())} thread(s)")

    codes = {f.code for f in findings}
    if codes & _CORRUPTION_CODES:
        status = CODE_CORRUPTION
    elif codes & _HOST_CODES:
        status = CODE_HOST_INSUFFICIENT
    elif manifest is None:
        status = CODE_INCOMPLETE
    elif installed:
        status = CODE_READY
    elif cache_complete:
        status = CODE_READY_OFFLINE
    else:
        status = CODE_INCOMPLETE

    exit_code = {CODE_READY: 0, CODE_READY_OFFLINE: 0,
                 CODE_INCOMPLETE: EXIT_INCOMPLETE,
                 CODE_CORRUPTION: EXIT_CORRUPTION,
                 CODE_HOST_INSUFFICIENT: EXIT_HOST}[status]
    diagnosis = {
        "status": status,
        "platform": key,
        "release": manifest.release.model_dump() if manifest else None,
        "checks": checks,
        "findings": [f.as_dict() for f in findings],
    }
    return diagnosis, exit_code


def _stored_manifest(paths: Paths) -> RuntimeManifest | None:
    directory = paths.state / "manifests"
    if not directory.exists():
        return None
    for candidate in sorted(directory.glob("*.manifest.json"), reverse=True):
        try:
            return read_manifest_source(str(candidate))
        except (ManifestError, OSError):
            continue
    return None
