"""Subprocess CLI tests for the host-level setup/doctor commands."""

import json
import sys
from pathlib import Path

import pytest
from test_runtime import make_binary, make_manifest


def run_cli(*args, env):
    return subprocess_run([sys.executable, "-m", "archskillkit", *args], env)


def subprocess_run(cmd, env):
    import subprocess

    return subprocess.run(cmd, check=False, capture_output=True, text=True,
                          env=env)


@pytest.fixture()
def sandbox_env(tmp_path, monkeypatch):
    data = tmp_path / "data"
    cache = tmp_path / "cache"
    state = tmp_path / "state"
    for path in (data, cache, state, tmp_path / "home"):
        path.mkdir(exist_ok=True)
    monkeypatch.setenv("XDG_DATA_HOME", str(data))
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache))
    monkeypatch.setenv("XDG_STATE_HOME", str(state))
    return {
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "HOME": str(tmp_path / "home"),
        "XDG_DATA_HOME": str(data),
        "XDG_CACHE_HOME": str(cache),
        "XDG_STATE_HOME": str(state),
    }


class TestRuntimeCli:
    def test_doctor_before_setup_is_incomplete(self, sandbox_env, tmp_path):
        proc = run_cli("doctor", env=sandbox_env)
        assert proc.returncode == 1, proc.stderr
        diagnosis = json.loads(proc.stdout)
        assert diagnosis["status"] == "incomplete"

    def test_setup_then_doctor_ready(self, sandbox_env, tmp_path):
        manifest_path = tmp_path / "runtime.manifest.json"
        manifest_path.write_text(
            make_manifest([make_binary(tmp_path, "ast-grep")]))
        proc = run_cli("setup", "--manifest", str(manifest_path),
                       env=sandbox_env)
        assert proc.returncode == 0, proc.stderr
        receipt = json.loads(proc.stdout)
        assert receipt["result"] == "installed"

        doctor = run_cli("doctor", env=sandbox_env)
        assert doctor.returncode == 0, doctor.stderr
        diagnosis = json.loads(doctor.stdout)
        assert diagnosis["status"] == "ready"
        assert diagnosis["release"]["version"] == "0.2.0"

    def test_setup_stores_manifest_for_offline_doctor(self, sandbox_env,
                                                      tmp_path):
        manifest_path = tmp_path / "runtime.manifest.json"
        manifest_path.write_text(
            make_manifest([make_binary(tmp_path, "ast-grep")]))
        assert run_cli("setup", "--manifest", str(manifest_path),
                       env=sandbox_env).returncode == 0
        stored = Path(sandbox_env["XDG_STATE_HOME"]) / "arch-skillkit" \
            / "manifests" / "v0.2.0.manifest.json"
        assert stored.is_file()

    def test_setup_failure_prints_finding_and_exit_2(self, sandbox_env,
                                                     tmp_path):
        manifest_path = tmp_path / "runtime.manifest.json"
        manifest_path.write_text(
            make_manifest([make_binary(tmp_path, "ast-grep")]))
        proc = run_cli("setup", "--manifest", str(manifest_path),
                       "--offline", env=sandbox_env)
        assert proc.returncode == 2
        finding = json.loads(proc.stdout)
        assert finding["code"] == "CACHE_MISSING"
        assert finding["remedy"]

    def test_setup_prefetch_then_offline_install(self, sandbox_env, tmp_path):
        manifest_path = tmp_path / "runtime.manifest.json"
        manifest_path.write_text(
            make_manifest([make_binary(tmp_path, "ast-grep")]))
        assert run_cli("setup", "--manifest", str(manifest_path), "--prefetch",
                       env=sandbox_env).returncode == 0
        doctor = run_cli("doctor", env=sandbox_env)
        assert json.loads(doctor.stdout)["status"] == "ready-offline"
        proc = run_cli("setup", "--manifest", str(manifest_path), "--offline",
                       env=sandbox_env)
        assert proc.returncode == 0, proc.stderr
        doctor = run_cli("doctor", env=sandbox_env)
        assert json.loads(doctor.stdout)["status"] == "ready"

    def test_doctor_rejects_unreadable_manifest(self, sandbox_env, tmp_path):
        proc = run_cli("doctor", "--manifest",
                       str(tmp_path / "missing.json"), env=sandbox_env)
        assert proc.returncode == 2
        assert "manifest" in proc.stderr

    def test_invalid_manifest_json_is_rejected(self, sandbox_env, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not json")
        proc = run_cli("setup", "--manifest", str(bad), env=sandbox_env)
        assert proc.returncode == 2
