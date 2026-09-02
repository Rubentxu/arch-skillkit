"""Fitness Profile, waivers and gate (V2.4 M3, docs/v2/59).

Gates: deterministic profile and verdict (same inputs -> identical
result); explicit N/A semantics; expired waiver fails the configured
gate; exit codes 0/1; gate operations never touch the world event log.
"""

import subprocess
from pathlib import Path

import pytest
import yaml
from jsonschema import validate as js_validate

from archskillkit.application.queries.fitness import (
    FitnessThresholds,
    compute_fitness,
    evaluate_gate,
)
from archskillkit.application.snapshot_builder import build_snapshot
from archskillkit.codeindex import CodeIndex
from archskillkit.runtime_state.run_ledger import (
    InMemoryRunLedgerStore,
    RunLedger,
    RunRecord,
)
from archskillkit.runtime_state.waivers import WaiverLedger
from archskillkit.world import ArchitectureWorld


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
def uncovered_world(sandbox, repo):
    """Coverage 0.5 (one element claimed), 1 unknown -> only
    evidence_coverage fails."""
    world = ArchitectureWorld.for_repo(repo).open()
    world.ensure_project()
    world.add_architecture_element("Orders API", "container")
    world.add_architecture_element("Billing", "component")
    from archskillkit.packs.arch_core import (
        ClaimData,
        EvidenceData,
        ObservationData,
    )
    obs = world.record_observation(ObservationData(
        subject="orders-api", predicate="exposes", object="GET /x",
        evidence=EvidenceData(tool="semgrep", rule="r", file="f.py",
                              start_line=1)))
    ev = world.record_evidence(EvidenceData(
        tool="semgrep", rule="r2", file="g.py", start_line=2))
    claim = world.propose_derived_claim(
        ClaimData(statement="orders api works", subjects=["Orders API"],
                  evidence_refs=[ev]), obs)
    world.accept_claim(claim)
    yield world
    world.close()


@pytest.fixture()
def bare_world(sandbox, repo):
    world = ArchitectureWorld.for_repo(repo).open()
    world.ensure_project()
    yield world
    world.close()


@pytest.fixture()
def world(sandbox, repo):
    """World whose only element is backed by an accepted claim ->
    full evidence coverage."""
    world = ArchitectureWorld.for_repo(repo).open()
    world.ensure_project()
    world.add_architecture_element("Orders API", "container")
    from archskillkit.packs.arch_core import (
        ClaimData,
        EvidenceData,
        ObservationData,
    )
    obs = world.record_observation(ObservationData(
        subject="orders-api", predicate="exposes", object="GET /x",
        evidence=EvidenceData(tool="semgrep", rule="r", file="f.py",
                              start_line=1)))
    ev = world.record_evidence(EvidenceData(
        tool="semgrep", rule="r2", file="g.py", start_line=2))
    claim = world.propose_derived_claim(
        ClaimData(statement="orders api works", subjects=["Orders API"],
                  evidence_refs=[ev]), obs)
    world.accept_claim(claim)
    yield world
    world.close()


@pytest.fixture()
def snapshot(world):
    index = CodeIndex(world.workspace / "code.sqlite").open()
    try:
        return build_snapshot(world, code_index=index)
    finally:
        index.close()


class TestFitnessProfile:
    def test_deterministic_for_same_inputs(self, world, snapshot):
        first = compute_fitness(world, snapshot)
        again = compute_fitness(world, snapshot)
        assert first.model_dump() == again.model_dump()

    def test_matches_design_schema(self, world, snapshot):
        schema = yaml.safe_load(
            (Path(__file__).resolve().parents[2]
             / "design/schemas/v2.4/fitness-profile.yaml").read_text())
        js_validate(compute_fitness(world, snapshot).model_dump(), schema)

    def test_na_is_explicit_not_hidden(self, bare_world):
        index = CodeIndex(bare_world.workspace / "code.sqlite").open()
        try:
            snapshot = build_snapshot(bare_world, code_index=index)
        finally:
            index.close()
        profile = compute_fitness(bare_world, snapshot)
        assert profile.dimensions["evidence_coverage"].status == "na"
        assert profile.dimensions["sensor_coverage"].status == "na"
        assert profile.dimensions["sensor_coverage"].value == \
            "not instrumented in M3"

    def test_coverage_pass_and_fail(self, uncovered_world):
        index = CodeIndex(uncovered_world.workspace / "code.sqlite").open()
        try:
            snapshot = build_snapshot(uncovered_world, code_index=index)
        finally:
            index.close()
        passed = compute_fitness(uncovered_world, snapshot,
                                 FitnessThresholds(
                                     min_evidence_coverage=0.5))
        # coverage 0.5 (1 of 2 elements claimed) >= 0.5 -> pass
        assert passed.dimensions["evidence_coverage"].status == "pass"
        failed = compute_fitness(uncovered_world, snapshot,
                                 FitnessThresholds(
                                     min_evidence_coverage=1.0))
        # 0.5 < 1.0 -> fail
        assert failed.dimensions["evidence_coverage"].status == "fail"

    def test_policy_coverage_na_without_rules(self, world, snapshot):
        profile = compute_fitness(world, snapshot)
        assert profile.dimensions["policy_coverage"].status == "na"

    def test_policy_coverage_pass_with_rules(self, world, snapshot):
        world.policies.record_rule(
            "no-ui-to-domain", "UI must not import domain",
            forbidden_relation="imports", source_category="ui",
            target_category="domain")
        profile = compute_fitness(world, snapshot)
        assert profile.dimensions["policy_coverage"].status == "pass"
        assert profile.dimensions["policy_coverage"].value == 1

    def test_freshness_na_without_ledger_and_pass_with_fresh_run(
            self, world, snapshot):
        profile = compute_fitness(world, snapshot)
        assert profile.dimensions["freshness"].status == "na"

        ledger = RunLedger(store=InMemoryRunLedgerStore())
        ledger.start(RunRecord(run_id="r1", kind="discover",
                               project_revision="abc",
                               started_at=utcnow_iso()))
        ledger.finish("r1", "PASS")
        fresh = compute_fitness(world, snapshot, ledger=ledger)
        assert fresh.dimensions["freshness"].status == "pass"
        assert fresh.dimensions["freshness"].evidence_refs == ["r1"]


def utcnow_iso() -> str:
    import datetime as _dt
    return _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class TestGate:
    def test_gate_pass_and_fail_exit_codes(self, world, snapshot):
        thresholds = FitnessThresholds(min_evidence_coverage=0.5)
        result = evaluate_gate(world, snapshot, thresholds=thresholds,
                               waivers=WaiverLedger(root=sandbox_fail()))
        assert result.verdict == "pass"
        assert result.exit_code == 0

        # unknown_coverage threshold of 1 is exceeded because the
        # accepted claim covers Orders API but Billing (added below)
        # is still unknown.
        world.add_architecture_element("Billing", "component")
        index = CodeIndex(world.workspace / "code.sqlite").open()
        try:
            snapshot2 = build_snapshot(world, code_index=index)
        finally:
            index.close()
        strict = FitnessThresholds(min_evidence_coverage=0.5,
                                   max_unknowns=0)
        result = evaluate_gate(world, snapshot2, thresholds=strict,
                               waivers=WaiverLedger(root=sandbox_fail()))
        assert result.verdict == "fail"
        assert result.exit_code == 1
        assert "unknown_coverage" in result.failed_dimensions

    def test_gate_is_deterministic(self, world, snapshot):
        thresholds = FitnessThresholds(min_evidence_coverage=1.0)
        first = evaluate_gate(world, snapshot, thresholds=thresholds,
                              waivers=WaiverLedger(root=sandbox_fail()))
        again = evaluate_gate(world, snapshot, thresholds=thresholds,
                              waivers=WaiverLedger(root=sandbox_fail()))
        assert first.model_dump() == again.model_dump()

    def test_active_waiver_downgrades_fail_to_warn(self, uncovered_world,
                                                   sandbox):
        ledger = WaiverLedger(root=sandbox / "waiv")
        ledger.grant("evidence_coverage", "legacy module onboarding",
                     granted_by="arch-team", expires_at="2999-12-31")
        index = CodeIndex(uncovered_world.workspace / "code.sqlite").open()
        try:
            snapshot = build_snapshot(uncovered_world, code_index=index)
        finally:
            index.close()
        strict = FitnessThresholds(min_evidence_coverage=1.0,
                                   max_unknowns=1)
        result = evaluate_gate(uncovered_world, snapshot,
                               thresholds=strict, waivers=ledger)
        assert result.verdict == "pass"
        assert result.waived[0]["dimension"] == "evidence_coverage"
        assert result.dimensions["evidence_coverage"].status == "warn"

    def test_expired_waiver_fails_the_gate(self, uncovered_world, sandbox):
        ledger = WaiverLedger(root=sandbox / "waiv")
        ledger.grant("evidence_coverage", "old exception",
                     granted_by="arch-team", expires_at="2020-01-01")
        index = CodeIndex(uncovered_world.workspace / "code.sqlite").open()
        try:
            snapshot = build_snapshot(uncovered_world, code_index=index)
        finally:
            index.close()
        strict = FitnessThresholds(min_evidence_coverage=1.0,
                                   max_unknowns=1)
        result = evaluate_gate(uncovered_world, snapshot,
                               thresholds=strict, waivers=ledger)
        assert result.verdict == "fail"
        assert result.expired_waivers[0]["dimension"] == \
            "evidence_coverage"
        assert result.failed_dimensions == ["evidence_coverage"]


def sandbox_fail() -> Path:
    """A throwaway waiver root: no waivers granted."""
    import tempfile
    return Path(tempfile.mkdtemp()) / "waivers"


class TestGateWorldIsolation:
    def test_gate_never_touches_world_event_log(self, world, snapshot):
        before = len(world.graph.events)
        evaluate_gate(world, snapshot, thresholds=FitnessThresholds(),
                      waivers=WaiverLedger(root=sandbox_fail()))
        assert len(world.graph.events) == before
