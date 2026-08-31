"""CLI facade tests: `python -m archskillkit` — the agent-facing seam."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from archskillkit.ids import compute_project_id


@pytest.fixture()
def repo(tmp_path):
    repo = tmp_path / "fixture"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "remote", "add", "origin", "https://github.com/rubentxu/fixture.git")
    return repo


def run_cli(*args, env):
    return subprocess.run(
        [sys.executable, "-m", "archskillkit", *args],
        check=False, capture_output=True, text=True, env=env,
    )


class TestCli:
    def test_init_registers_project(self, repo, tmp_path, monkeypatch):
        env = _sandbox_env(monkeypatch, tmp_path)
        proc = run_cli("init", "--repo", str(repo), env=env)
        assert proc.returncode == 0, proc.stderr
        out = json.loads(proc.stdout)
        assert out["project_id"] == compute_project_id(
            str(repo.resolve()), "github.com/rubentxu/fixture")
        assert Path(out["workspace"]).is_dir()
        assert Path(out["activegraph_db"]).is_file()

    def test_state_and_replay_verify(self, repo, tmp_path, monkeypatch):
        env = _sandbox_env(monkeypatch, tmp_path)
        assert run_cli("init", "--repo", str(repo), env=env).returncode == 0

        payload = tmp_path / "obs.json"
        payload.write_text(json.dumps({
            "subject": "domain.orders", "predicate": "exposes",
            "object": "POST /orders",
            "evidence": {"tool": "semgrep", "rule": "spring.endpoint",
                         "file": "Orders.kt", "start_line": 10},
        }))
        proc = run_cli("record-observation", "--repo", str(repo),
                       "--payload", str(payload), env=env)
        assert proc.returncode == 0, proc.stderr

        state = json.loads(run_cli("state", "--repo", str(repo), env=env).stdout)
        assert state["counts"]["observation"] == 1

        verify = run_cli("replay-verify", "--repo", str(repo), env=env)
        assert verify.returncode == 0, verify.stderr
        assert "replay OK" in verify.stdout

    def test_replay_verify_unknown_project_fails_cleanly(self, tmp_path, monkeypatch):
        env = _sandbox_env(monkeypatch, tmp_path)
        ghost = tmp_path / "ghost"
        ghost.mkdir()
        _git(ghost, "init", "-q")
        proc = run_cli("replay-verify", "--repo", str(ghost), env=env)
        assert proc.returncode == 1
        assert "no Architecture World" in (proc.stderr + proc.stdout)

    def test_init_outside_repo_fails(self, tmp_path, monkeypatch):
        env = _sandbox_env(monkeypatch, tmp_path)
        bare = tmp_path / "not-a-repo"
        bare.mkdir()
        proc = run_cli("init", "--repo", str(bare), env=env)
        assert proc.returncode == 2
        assert "not a git repository" in proc.stderr


def _sandbox_env(monkeypatch, tmp_path):
    env = {
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "HOME": str(tmp_path / "home"),
        "XDG_DATA_HOME": str(tmp_path / "data"),
        "XDG_STATE_HOME": str(tmp_path / "state"),
    }
    (tmp_path / "home").mkdir(exist_ok=True)
    return env


def _git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)
