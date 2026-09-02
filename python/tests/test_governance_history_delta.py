"""GetHistory + ArchitectureDelta golden tests (V2.4 M3, docs/v2/59).

Gates: history serves 3+ real recorded runs; the delta between two
world states is byte-stable against a committed golden file and changes
when the head state changes.
"""

import json
import subprocess
from pathlib import Path

import pytest

from archskillkit.application.queries.delta import compute_delta
from archskillkit.application.queries.history import get_history
from archskillkit.runtime_state.run_ledger import (
    InMemoryRunLedgerStore,
    RunLedger,
    RunRecord,
)
from archskillkit.world import ArchitectureWorld

GOLDEN = Path(__file__).resolve().parents[2] / "tests" / "golden" / \
    "architecture-delta-v1.json"


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args],
                   check=True, capture_output=True)


@pytest.fixture()
def sandbox(monkeypatch, tmp_path):
    data = tmp_path / "data"
    monkeypatch.setenv("XDG_DATA_HOME", str(data))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "runtime"))
    return data


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


@pytest.fixture()
def worlds(sandbox, repo):
    """Two sibling runs of the same project: delta-base (v1) and
    delta-head (v2) with known changes: element added + removed +
    confidence changed; relation added + removed; a gap difference."""
    anchor = ArchitectureWorld.for_repo(repo).open()
    anchor.ensure_project()
    anchor.close()

    base = ArchitectureWorld.for_repo(repo).view("delta-base")
    base.ensure_project()
    base.add_architecture_element("Orders API", "container")
    base.add_architecture_element("Legacy Cron", "component",
                                  origin="INFERRED", confidence="low")
    base.add_architecture_element("Billing", "component",
                                  confidence="medium")
    b = base.find_objects("architecture_element", name="Billing")[0]["id"]
    o = base.find_objects("architecture_element", name="Orders API")[0]["id"]
    base.add_architecture_relation("depends_on", o, b)
    base.policies.record_rule(
        "no-ui-to-domain", "UI must not import domain",
        forbidden_relation="imports", source_category="ui",
        target_category="domain")
    base.record_knowledge_gap("who owns billing?")
    base.close()

    head = ArchitectureWorld.for_repo(repo).view("delta-head")
    head.ensure_project()
    head.add_architecture_element("Orders API", "container")
    head.add_architecture_element("Legacy Cron", "component",
                                  origin="INFERRED", confidence="medium")
    head.add_architecture_element("Billing", "component",
                                  confidence="high")
    head.add_architecture_element("Notifications", "component")
    b = head.find_objects("architecture_element", name="Billing")[0]["id"]
    o = head.find_objects("architecture_element",
                          name="Orders API")[0]["id"]
    n = head.find_objects("architecture_element",
                          name="Notifications")[0]["id"]
    head.add_architecture_relation("exposes", o, n)
    # resolve one unknown: accepted claim covering Billing
    from archskillkit.packs.arch_core import (
        ClaimData,
        EvidenceData,
        ObservationData,
    )
    obs = head.record_observation(ObservationData(
        subject="billing", predicate="charges", object="users",
        evidence=EvidenceData(tool="semgrep", rule="r", file="b.py",
                              start_line=1)))
    ev = head.record_evidence(EvidenceData(
        tool="semgrep", rule="r2", file="b.py", start_line=2))
    claim = head.propose_derived_claim(
        ClaimData(statement="Billing charges users",
                  subjects=["Billing"], evidence_refs=[ev]), obs)
    head.accept_claim(claim)
    obs2 = head.record_observation(ObservationData(
        subject="orders", predicate="exposes", object="POST /orders",
        evidence=EvidenceData(tool="semgrep", rule="r3", file="o.py",
                              start_line=3)))
    ev2 = head.record_evidence(EvidenceData(
        tool="semgrep", rule="r4", file="o.py", start_line=4))
    claim2 = head.propose_derived_claim(
        ClaimData(statement="Orders API exposes POST /orders",
                  subjects=["Orders API"], evidence_refs=[ev2]), obs2)
    head.accept_claim(claim2)
    head.close()

    base = ArchitectureWorld.for_repo(repo).view("delta-base")
    head = ArchitectureWorld.for_repo(repo).view("delta-head")
    yield base, head
    base.close()
    head.close()


class TestGetHistory:
    def test_history_serves_three_plus_real_runs(self):
        ledger = RunLedger(store=InMemoryRunLedgerStore())
        for i, day in enumerate(["2026-09-01", "2026-09-02", "2026-09-03"]):
            rid = f"run-{i}"
            ledger.start(RunRecord(run_id=rid, kind="discover",
                                   project_revision="abc",
                                   started_at=f"{day}T00:00:00Z"))
            ledger.finish(rid, "PASS" if i != 1 else "FAIL")
        history = get_history(ledger)
        assert history.total_matching == 3
        assert [r.run_id for r in history.runs] == \
            ["run-2", "run-1", "run-0"]
        assert history.runs[1].status == "FAIL"

    def test_history_filter_and_limit(self):
        ledger = RunLedger(store=InMemoryRunLedgerStore())
        for i in range(5):
            rid = f"r{i}"
            ledger.start(RunRecord(run_id=rid, kind="drift",
                                   project_revision="abc",
                                   started_at=f"2026-09-0{i + 1}T00:00:00Z"))
            ledger.finish(rid, "PASS")
        history = get_history(ledger, limit=2, status="PASS")
        assert history.total_matching == 5
        assert history.returned == 2


class TestArchitectureDelta:
    def test_delta_matches_committed_golden(self, worlds):
        base, head = worlds
        delta = compute_delta(base, head,
                              base_snapshot_id="snap-base",
                              head_snapshot_id="snap-head")
        actual = json.dumps(delta.model_dump(), indent=2,
                            sort_keys=True) + "\n"
        if not GOLDEN.exists() or os_environ_flag():
            GOLDEN.parent.mkdir(parents=True, exist_ok=True)
            GOLDEN.write_text(actual)
            pytest.fail("golden file was (re)written; review and commit")
        assert actual == GOLDEN.read_text()

    def test_empty_delta_for_identical_states(self, worlds):
        base, _ = worlds
        twin = compute_delta(base, base, "s", "s")
        assert twin.elements.added == twin.elements.removed == []
        assert twin.elements.changed == []
        assert twin.relations.added == twin.relations.removed == []
        assert twin.unknowns["delta"] == 0

    def test_unknowns_and_drift_move(self, worlds):
        base, head = worlds
        delta = compute_delta(base, head)
        # base: 3 uncovered elements; head covers Orders API and
        # Billing via accepted claims but adds Notifications -> 2
        assert delta.unknowns == {"base": 3, "head": 2, "delta": -1}


def os_environ_flag() -> bool:
    import os
    return os.environ.get("UPDATE_GOLDEN") == "1"
