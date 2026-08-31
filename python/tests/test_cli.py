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


class TestCodeIndexCli:
    def test_ingest_stats_search_roundtrip(self, repo, tmp_path, monkeypatch):
        env = _sandbox_env(monkeypatch, tmp_path)
        assert run_cli("init", "--repo", str(repo), env=env).returncode == 0

        astgrep = tmp_path / "outline.json"
        astgrep.write_text(json.dumps({
            "ruleId": "outline.kotlin.function", "text": "get_orders",
            "file": "src/Orders.kt", "language": "Kotlin",
            "range": {"start": {"line": 4, "column": 0}},
            "lines": "fun get_orders() {}", "metaVariables": {"single": {}, "multi": {}},
        }) + "\n")
        semgrep = tmp_path / "patterns.json"
        semgrep.write_text(json.dumps({"results": [{
            "check_id": "spring.endpoint", "path": "src/Orders.kt",
            "start": {"line": 5, "col": 1}, "end": {"line": 5, "col": 20},
            "extra": {"message": "endpoint", "metavars": {}, "lines": ""},
        }]}))

        proc = run_cli("ingest-code", "--repo", str(repo),
                       "--astgrep", str(astgrep), "--semgrep", str(semgrep),
                       "--run-id", "r1", env=env)
        assert proc.returncode == 0, proc.stderr
        report = json.loads(proc.stdout)
        assert report["symbols"] == 2  # handler + endpoint pseudo-symbol
        assert report["edges"] == 1

        stats = json.loads(run_cli("index-stats", "--repo", str(repo), env=env).stdout)
        assert stats["symbols"] == 2 and stats["edges"] == 1

        hits = json.loads(run_cli("search-code", "--repo", str(repo),
                                  "orders", env=env).stdout)
        assert len(hits) == 1 and hits[0]["name"] == "get_orders"

    def test_index_stats_without_index_fails_cleanly(self, repo, tmp_path, monkeypatch):
        env = _sandbox_env(monkeypatch, tmp_path)
        assert run_cli("init", "--repo", str(repo), env=env).returncode == 0
        proc = run_cli("index-stats", "--repo", str(repo), env=env)
        assert proc.returncode == 1
        assert "no code.sqlite" in proc.stderr

    def test_ingest_requires_at_least_one_payload(self, repo, tmp_path, monkeypatch):
        env = _sandbox_env(monkeypatch, tmp_path)
        proc = run_cli("ingest-code", "--repo", str(repo),
                       "--run-id", "r1", env=env)
        assert proc.returncode == 2


class TestPromotionCli:
    def test_discover_and_review_roundtrip(self, repo, tmp_path, monkeypatch):
        env = _sandbox_env(monkeypatch, tmp_path)
        assert run_cli("init", "--repo", str(repo), env=env).returncode == 0

        astgrep = tmp_path / "outline.json"
        astgrep.write_text(json.dumps({
            "ruleId": "outline.kotlin.function", "text": "get_orders",
            "file": "src/Orders.kt", "language": "Kotlin",
            "range": {"start": {"line": 4, "column": 0}},
            "lines": "fun get_orders() {}", "metaVariables": {"single": {}, "multi": {}},
        }) + "\n")
        semgrep = tmp_path / "patterns.json"
        semgrep.write_text(json.dumps({"results": [{
            "check_id": "spring.endpoint", "path": "src/Orders.kt",
            "start": {"line": 5, "col": 1}, "end": {"line": 5, "col": 20},
            "extra": {"message": "endpoint", "metavars": {}, "lines": ""},
        }]}))
        assert run_cli("ingest-code", "--repo", str(repo),
                       "--astgrep", str(astgrep), "--semgrep", str(semgrep),
                       "--run-id", "r1", env=env).returncode == 0

        before = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain"],
            capture_output=True, text=True).stdout

        proc = run_cli("discover", "--repo", str(repo), "--run-id", "r1", env=env)
        assert proc.returncode == 0, proc.stderr
        report = json.loads(proc.stdout)
        assert report["observations"] == 1
        assert report["claims_accepted"] == 1
        assert report["elements"] == 2  # component + external_system
        assert report["relations"] == 1
        assert report["findings"] == 0

        proc = run_cli("review", "--repo", str(repo), env=env)
        assert proc.returncode == 0, proc.stderr
        assert json.loads(proc.stdout)["findings"] == []

        after = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain"],
            capture_output=True, text=True).stdout
        assert after == before  # UAT-001 through the whole pipeline

    def test_discover_without_code_index_fails_cleanly(self, repo, tmp_path, monkeypatch):
        env = _sandbox_env(monkeypatch, tmp_path)
        assert run_cli("init", "--repo", str(repo), env=env).returncode == 0
        proc = run_cli("discover", "--repo", str(repo), "--run-id", "r1", env=env)
        assert proc.returncode == 1
        assert "no code.sqlite" in proc.stderr


class TestContextCli:
    def test_context_pack_via_cli(self, repo, tmp_path, monkeypatch):
        env = _sandbox_env(monkeypatch, tmp_path)
        assert run_cli("init", "--repo", str(repo), env=env).returncode == 0
        astgrep = tmp_path / "outline.json"
        astgrep.write_text(json.dumps({
            "ruleId": "outline.kotlin.function", "text": "get_orders",
            "file": "src/Orders.kt", "language": "Kotlin",
            "range": {"start": {"line": 4, "column": 0}},
            "lines": "fun get_orders() {}", "metaVariables": {"single": {}, "multi": {}},
        }) + "\n")
        semgrep = tmp_path / "patterns.json"
        semgrep.write_text(json.dumps({"results": [{
            "check_id": "spring.endpoint", "path": "src/Orders.kt",
            "start": {"line": 5, "col": 1}, "end": {"line": 5, "col": 20},
            "extra": {"message": "endpoint", "metavars": {}, "lines": ""},
        }]}))
        assert run_cli("ingest-code", "--repo", str(repo),
                       "--astgrep", str(astgrep), "--semgrep", str(semgrep),
                       "--run-id", "r1", env=env).returncode == 0
        assert run_cli("discover", "--repo", str(repo),
                       "--run-id", "r1", env=env).returncode == 0

        proc = run_cli("context", "--repo", str(repo),
                       "--goal", "overview of orders", "--max-nodes", "5", env=env)
        assert proc.returncode == 0, proc.stderr
        pack = json.loads(proc.stdout)
        assert pack["schema_version"] == 1
        assert len(pack["architecture"]["elements"]) <= 5
        assert pack["budget"]["max_nodes"] == 5
        assert pack["metrics"]["context_reads"] == 1

    def test_context_without_world_fails_cleanly(self, repo, tmp_path, monkeypatch):
        env = _sandbox_env(monkeypatch, tmp_path)
        assert run_cli("init", "--repo", str(repo), env=env).returncode == 0
        proc = run_cli("context", "--repo", str(repo),
                       "--goal", "overview", env=env)
        assert proc.returncode == 1
        assert "no code.sqlite" in proc.stderr


class TestProjectCli:
    @staticmethod
    def _seed_pipeline(repo, tmp_path, env):
        assert run_cli("init", "--repo", str(repo), env=env).returncode == 0
        astgrep = tmp_path / "outline.json"
        astgrep.write_text(json.dumps({
            "ruleId": "outline.kotlin.function", "text": "get_orders",
            "file": "src/Orders.kt", "language": "Kotlin",
            "range": {"start": {"line": 4, "column": 0}},
            "lines": "fun get_orders() {}", "metaVariables": {"single": {}, "multi": {}},
        }) + "\n")
        semgrep = tmp_path / "patterns.json"
        semgrep.write_text(json.dumps({"results": [{
            "check_id": "spring.endpoint", "path": "src/Orders.kt",
            "start": {"line": 5, "col": 1}, "end": {"line": 5, "col": 20},
            "extra": {"message": "endpoint", "metavars": {}, "lines": ""},
        }]}))
        assert run_cli("ingest-code", "--repo", str(repo),
                       "--astgrep", str(astgrep), "--semgrep", str(semgrep),
                       "--run-id", "r1", env=env).returncode == 0
        assert run_cli("discover", "--repo", str(repo),
                       "--run-id", "r1", env=env).returncode == 0

    def test_project_generates_both_artifacts(self, repo, tmp_path, monkeypatch):
        env = _sandbox_env(monkeypatch, tmp_path)
        self._seed_pipeline(repo, tmp_path, env)
        proc = run_cli("project", "--repo", str(repo), env=env)
        assert proc.returncode == 0, proc.stderr
        out = json.loads(proc.stdout)
        formats = {p["format"] for p in out["projections"]}
        assert formats == {"likec4", "arrows"}
        for projection in out["projections"]:
            assert Path(projection["path"]).is_file()
            assert Path(projection["path"] + ".meta.json").is_file()
        model = Path(out["projections"][0]["path"])
        arrows = Path(out["projections"][1]["path"])
        assert "specification {" in model.read_text()
        assert json.loads(arrows.read_text())["schema"] == "arch-skillkit/arrows-v1"

    def test_project_without_world_fails_cleanly(self, repo, tmp_path, monkeypatch):
        env = _sandbox_env(monkeypatch, tmp_path)
        # no init: the repo has no Architecture World yet
        proc = run_cli("project", "--repo", str(repo), env=env)
        assert proc.returncode == 1
        assert "no Architecture World" in proc.stderr


class TestDriftCli:
    def test_drift_report_on_clean_world(self, repo, tmp_path, monkeypatch):
        env = _sandbox_env(monkeypatch, tmp_path)
        TestProjectCli._seed_pipeline(repo, tmp_path, env)
        proc = run_cli("drift", "--repo", str(repo), env=env)
        assert proc.returncode == 0, proc.stderr
        report = json.loads(proc.stdout)
        assert report["drift"]["findings"] == []  # no rules declared yet
        assert report["stale_model"]["findings"] == []

    def test_drift_without_world_fails_cleanly(self, repo, tmp_path, monkeypatch):
        env = _sandbox_env(monkeypatch, tmp_path)
        proc = run_cli("drift", "--repo", str(repo), env=env)
        assert proc.returncode == 1
        assert "no Architecture World" in proc.stderr


class TestForkCli:
    def test_fork_diff_reject_flow(self, repo, tmp_path, monkeypatch):
        env = _sandbox_env(monkeypatch, tmp_path)
        TestProjectCli._seed_pipeline(repo, tmp_path, env)

        proc = run_cli("fork", "--repo", str(repo), "--name", "async", env=env)
        assert proc.returncode == 0, proc.stderr
        assert json.loads(proc.stdout)["run_id"] == "proposal-async"

        proc = run_cli("diff", "--repo", str(repo), "--name", "async", env=env)
        assert proc.returncode == 0, proc.stderr
        assert json.loads(proc.stdout)["is_empty"] is True

        proc = run_cli("reject-proposal", "--repo", str(repo),
                       "--name", "async", "--actor", "architect", env=env)
        assert proc.returncode == 0, proc.stderr

        # rejected proposals never promote
        proc = run_cli("promote", "--repo", str(repo), "--name", "async",
                       "--approved-by", "architect", env=env)
        assert proc.returncode == 1
        assert "rejected" in proc.stderr

    def test_fork_requires_world(self, repo, tmp_path, monkeypatch):
        env = _sandbox_env(monkeypatch, tmp_path)
        proc = run_cli("fork", "--repo", str(repo), "--name", "x", env=env)
        assert proc.returncode == 1
        assert "no Architecture World" in proc.stderr

    def test_diff_unknown_fork_fails_cleanly(self, repo, tmp_path, monkeypatch):
        env = _sandbox_env(monkeypatch, tmp_path)
        TestProjectCli._seed_pipeline(repo, tmp_path, env)
        proc = run_cli("diff", "--repo", str(repo), "--name", "ghost", env=env)
        assert proc.returncode == 1
        assert "no fork run" in proc.stderr


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
