"""Control Plane kernel end-to-end (V2.4 M5 slice 20, docs/v2/59 M5
"local-only server default").

Spawns the real server as a subprocess on an ephemeral port and
exercises the HTTP surface:

- binds loopback only (BIND_HOST constant, no escape hatch)
- every request requires the bearer token (401 + stable code
  otherwise, including wrong method probes)
- /status, /history, /viewers return the same schema-bound envelopes
  as their CLI counterparts
- unknown route -> 404 NOT_FOUND, wrong verb -> 405 METHOD_NOT_ALLOWED
- RuntimeRegistry: registered while running, unregistered after a
  graceful SIGTERM; process exits 0
- no Architecture World -> exit code 2 with the standard message
"""

import json
import subprocess
import sys
import urllib.error
import urllib.request

import pytest

from archskillkit.delivery.cli.control_plane import BIND_HOST
from archskillkit.runtime_state.runtime_registry import RuntimeRegistry


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture()
def sandbox(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "runtime"))
    return tmp_path


@pytest.fixture()
def repo_with_world(tmp_path):
    repo = tmp_path / "fixture"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "main.rs").write_text("fn main() {}\n")
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")
    subprocess.run(
        [sys.executable, "-m", "archskillkit", "init", "--repo", str(repo)],
        check=True,
        capture_output=True,
    )
    return repo


@pytest.fixture()
def server(sandbox, repo_with_world):
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "archskillkit",
            "control-plane",
            "--repo",
            str(repo_with_world),
            "--port",
            "0",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    line = proc.stdout.readline()
    assert line.strip(), f"server died before startup line: {proc.stderr.read()}"
    start = json.loads(line)
    assert start["schema"] == "arch-skillkit/control-plane-start-v1"
    yield start
    proc.terminate()
    proc.wait(timeout=10)


def _get(url: str, token: str | None):
    req = urllib.request.Request(url)
    if token is not None:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


def _post(url: str, token: str):
    req = urllib.request.Request(
        url, data=b"{}", method="POST", headers={"Authorization": f"Bearer {token}"}
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


# ---------- binding / auth gates ---------------------------------------


def test_binds_loopback_only():
    """docs/v2/54 §12: localhost is enforced by construction."""
    assert BIND_HOST == "127.0.0.1"


def test_start_envelope_is_loopback(server):
    assert server["host"] == "127.0.0.1"
    assert server["url"].startswith("http://127.0.0.1:")
    assert server["runtime_registry"] == "registered"
    assert server["token"]


def test_missing_token_is_unauthorized(server):
    status, body = _get(server["url"] + "/status", token=None)
    assert status == 401
    assert body["code"] == "UNAUTHORIZED"


def test_wrong_token_is_unauthorized(server):
    status, body = _get(server["url"] + "/status", token="nope")
    assert status == 401
    assert body["code"] == "UNAUTHORIZED"


def test_health_requires_token_too(server):
    status_noauth, _ = _get(server["url"] + "/health", token=None)
    assert status_noauth == 401
    status, body = _get(server["url"] + "/health", token=server["token"])
    assert status == 200
    assert body == {"schema": "arch-skillkit/control-plane-health-v1", "ok": True}


def test_write_methods_rejected(server):
    status, body = _post(server["url"] + "/status", token=server["token"])
    assert status == 405
    assert body["code"] == "METHOD_NOT_ALLOWED"


# ---------- read endpoints (same envelopes as the CLI) ------------------


def test_status_endpoint(server):
    status, body = _get(server["url"] + "/status", token=server["token"])
    assert status == 200
    assert body["schema"] == "arch-skillkit/status-result-v1"
    assert body["project_id"]
    assert isinstance(body["suggestions"], list)
    assert "snapshot" in body


def test_history_endpoint_with_limit(server):
    status, body = _get(server["url"] + "/history?limit=1", token=server["token"])
    assert status == 200
    assert body["schema"] == "arch-skillkit/history-v1"
    assert body["returned"] <= 1


def test_history_rejects_garbage_limit(server):
    status, body = _get(server["url"] + "/history?limit=abc", token=server["token"])
    assert status == 200
    assert body["schema"] == "arch-skillkit/history-v1"


def test_viewers_endpoint(server):
    status, body = _get(server["url"] + "/viewers", token=server["token"])
    assert status == 200
    assert body["schema"] == "arch-skillkit/viewers-v1"
    ids = {v["id"] for v in body["viewers"]}
    assert "likec4-server" in ids
    assert "system-default" in ids


def test_unknown_route_404(server):
    status, body = _get(server["url"] + "/nope", token=server["token"])
    assert status == 404
    assert body["code"] == "NOT_FOUND"


# ---------- runtime registry lifecycle ----------------------------------


def test_registry_registered_then_unregistered(sandbox, repo_with_world):
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "archskillkit",
            "control-plane",
            "--repo",
            str(repo_with_world),
            "--port",
            "0",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    start = json.loads(proc.stdout.readline())
    registry = RuntimeRegistry()
    pids = {e.pid for e in registry.active()}
    assert start["pid"] in pids
    assert start["project_id"] in {e.project_id for e in registry.active()}

    proc.terminate()
    assert proc.wait(timeout=10) == 0
    assert start["pid"] not in {e.pid for e in registry.active()}


def test_missing_world_exits_2(sandbox, tmp_path):
    """Two precondition failures, both exit 2: path outside a git work
    tree (RepoNotFound) and git repo without an initialized world."""
    empty = tmp_path / "empty"
    empty.mkdir()
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "archskillkit",
            "control-plane",
            "--repo",
            str(empty),
            "--port",
            "0",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 2
    assert "not a git repository" in proc.stderr


def test_git_repo_without_world_exits_2(sandbox, tmp_path):
    repo = tmp_path / "bare"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    proc = subprocess.run(
        [sys.executable, "-m", "archskillkit", "control-plane", "--repo", str(repo), "--port", "0"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 2
    assert "no Architecture World" in proc.stderr
