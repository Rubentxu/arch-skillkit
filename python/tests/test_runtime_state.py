"""RunLedger + RuntimeRegistry (V2.4 M0 Slice 3, ADR-0033).

Contracts: design/schemas/v2.4/run-record.yaml. M0 gates under test:
run summaries never enter the world event log; runtime state (PIDs)
lives under the XDG runtime root with orphan cleanup proven.
"""

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml
from jsonschema import validate as js_validate
from pydantic import ValidationError

from archskillkit.ids import arch_runtime_root
from archskillkit.runtime_state.run_ledger import (
    InMemoryRunLedgerStore,
    LedgerError,
    RunLedger,
    RunRecord,
    SqliteRunLedgerStore,
)
from archskillkit.runtime_state.runtime_registry import (
    RuntimeEntry,
    RuntimeRegistry,
)
from archskillkit.world import ArchitectureWorld

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "design" / "schemas" / "v2.4"


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args],
                   check=True, capture_output=True)


@pytest.fixture()
def sandbox(monkeypatch, tmp_path):
    data = tmp_path / "data"
    monkeypatch.setenv("XDG_DATA_HOME", str(data))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "runtime"))
    return tmp_path


@pytest.fixture()
def repo(tmp_path):
    repo = tmp_path / "fixture"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "main.rs").write_text("fn main() {}\n")
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")
    return repo


def _record(run_id="run-1", **kw) -> RunRecord:
    defaults: dict = {
        "kind": "discover",
        "project_revision": "abc123",
        "started_at": "2026-09-02T00:00:00Z",
    }
    defaults.update(kw)
    return RunRecord(run_id=run_id, **defaults)


class TestRunRecordContract:
    def test_matches_design_schema(self):
        schema = yaml.safe_load(
            (SCHEMA_DIR / "run-record.yaml").read_text())
        js_validate(_record(status="PASS").model_dump(), schema)

    def test_rejects_unknown_kind_status_and_extra(self):
        with pytest.raises(ValidationError):
            _record(kind="deploy")
        with pytest.raises(ValidationError):
            _record(status="MAYBE")
        with pytest.raises(ValidationError):
            _record(pid=123)

    def test_canonical_json_is_stable(self):
        assert _record().canonical_json() == _record().canonical_json()


class TestRunLedger:
    @pytest.mark.parametrize("store", [
        lambda: InMemoryRunLedgerStore(),
        lambda: SqliteRunLedgerStore(Path(":memory:")),
    ], ids=["in-memory", "sqlite"])
    def test_start_finish_roundtrip(self, store):
        ledger = RunLedger(store=store())
        ledger.start(_record())
        done = ledger.finish("run-1", "PASS",
                             metrics={"symbols": 42},
                             snapshot_after="snap-abc")
        assert done.status == "PASS"
        assert done.finished_at is not None
        assert done.metrics == {"symbols": 42}
        assert done.snapshot_after == "snap-abc"
        assert ledger.get("run-1").status == "PASS"

    def test_duplicate_start_refused(self):
        ledger = RunLedger(store=InMemoryRunLedgerStore())
        ledger.start(_record())
        with pytest.raises(LedgerError):
            ledger.start(_record())

    def test_unknown_run_refused(self):
        ledger = RunLedger(store=InMemoryRunLedgerStore())
        with pytest.raises(LedgerError):
            ledger.finish("nope", "PASS")
        with pytest.raises(LedgerError):
            ledger.get("nope")

    def test_list_newest_first_with_limit_and_filter(self):
        ledger = RunLedger(store=InMemoryRunLedgerStore())
        for i, (rid, at, st) in enumerate([
            ("a", "2026-09-01T00:00:00Z", "PASS"),
            ("b", "2026-09-02T00:00:00Z", "FAIL"),
            ("c", "2026-09-03T00:00:00Z", "PASS"),
        ]):
            ledger.start(_record(rid, started_at=at))
            ledger.finish(rid, st)
        assert [r.run_id for r in ledger.list()] == ["c", "b", "a"]
        assert [r.run_id for r in ledger.list(limit=1)] == ["c"]
        assert [r.run_id for r in ledger.list(status="PASS")] == ["c", "a"]

    def test_sqlite_store_persists_across_instances(self, tmp_path):
        db = tmp_path / "ledger.sqlite"
        first = RunLedger(store=SqliteRunLedgerStore(db))
        first.start(_record())
        second = RunLedger(store=SqliteRunLedgerStore(db))
        assert second.get("run-1").project_revision == "abc123"

    def test_default_path_lives_under_state_root(self, sandbox):
        ledger = RunLedger()
        ledger.start(_record())
        expected = sandbox / "state" / "arch-skillkit" / "run-ledger.sqlite"
        assert expected.is_file()


class TestLedgerWorldIsolation:
    def test_ledger_ops_never_touch_world_event_log(self, sandbox, repo):
        world = ArchitectureWorld.for_repo(repo).open()
        world.ensure_project()
        events_before = len(world.graph.events)
        assert events_before > 0

        ledger = RunLedger(store=InMemoryRunLedgerStore())
        ledger.start(_record())
        ledger.finish("run-1", "PASS", metrics={})
        registry = RuntimeRegistry()
        registry.register(RuntimeEntry(pid=os.getpid(), run_id="run-1"))
        registry.cleanup_orphans()
        registry.unregister(os.getpid())

        assert len(world.graph.events) == events_before
        world.close()


class TestRuntimeRegistry:
    def test_register_active_unregister(self, sandbox):
        reg = RuntimeRegistry()
        reg.register(RuntimeEntry(pid=100, run_id="r1", command="discover"))
        reg.register(RuntimeEntry(pid=101, run_id="r2"))
        entries = reg.active()
        assert [e.pid for e in entries] == [100, 101]
        assert entries[0].started_at != ""
        assert reg.unregister(100) is True
        assert reg.unregister(100) is False
        assert [e.pid for e in reg.active()] == [101]

    def test_same_pid_reregister_replaces(self, sandbox):
        reg = RuntimeRegistry()
        reg.register(RuntimeEntry(pid=7, run_id="old"))
        reg.register(RuntimeEntry(pid=7, run_id="new"))
        active = reg.active()
        assert len(active) == 1
        assert active[0].run_id == "new"

    def test_cleanup_orphans_reaps_dead_pids_keeps_live(
            self, sandbox, repo):
        reg = RuntimeRegistry()
        doomed = subprocess.Popen(["sleep", "30"])
        doomed.terminate()
        doomed.wait()
        assert not RuntimeRegistry._pid_alive(doomed.pid)

        reg.register(RuntimeEntry(pid=doomed.pid, run_id="dead"))
        reg.register(RuntimeEntry(pid=os.getpid(), run_id="alive"))

        removed = reg.cleanup_orphans()
        assert [e.run_id for e in removed] == ["dead"]
        assert [e.run_id for e in reg.active()] == ["alive"]

    def test_persists_across_instances(self, sandbox):
        RuntimeRegistry().register(RuntimeEntry(pid=1, run_id="keep"))
        again = RuntimeRegistry()
        assert [e.run_id for e in again.active()] == ["keep"]

    def test_default_root_follows_xdg_runtime_dir(self, sandbox):
        reg = RuntimeRegistry()
        assert reg.root == sandbox / "runtime" / "arch-skillkit"
        assert arch_runtime_root() == reg.root

    def test_registry_file_is_readable_json(self, sandbox):
        reg = RuntimeRegistry()
        reg.register(RuntimeEntry(pid=5, run_id="r"))
        doc = json.loads(reg.path.read_text())
        assert doc["version"] == 1
        assert doc["entries"][0]["pid"] == 5
