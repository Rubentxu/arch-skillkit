"""GetStatus / Explain use cases + application ports (V2.4 M0 Slice 2).

Contract: docs/v2/55 §2 (queries), §5 (typed suggestions), §10 (error
codes). The use cases consume ArchitectureQueryPort / GovernancePort —
never world.graph.
"""

import subprocess

import pytest
from pydantic import ValidationError

from archskillkit.application.models.actions import ActionSuggestion
from archskillkit.application.models.snapshot import snapshot_digest
from archskillkit.application.ports.architecture_query import (
    ArchitectureQueryPort,
)
from archskillkit.application.ports.governance import GovernancePort
from archskillkit.application.queries.explain import (
    Explanation,
    SubjectNotFound,
    explain,
)
from archskillkit.application.queries.get_status import (
    STATUS_SCHEMA,
    StatusResult,
    get_status,
)
from archskillkit.packs.arch_core import ClaimData, EvidenceData, ObservationData
from archskillkit.world import ArchitectureWorld


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args],
                   check=True, capture_output=True)


@pytest.fixture()
def sandbox(monkeypatch, tmp_path):
    data = tmp_path / "data"
    monkeypatch.setenv("XDG_DATA_HOME", str(data))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
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


class _FakeIndex:
    """Duck-typed CodeIndex: the builder only reads current_generation."""

    def __init__(self, generation="gen-1"):
        self._generation = generation

    @property
    def current_generation(self):
        return self._generation


@pytest.fixture()
def world(sandbox, repo):
    world = ArchitectureWorld.for_repo(repo).open()
    world.ensure_project()
    yield world
    world.close()


@pytest.fixture()
def populated(world):
    """A claim with real lineage: observation + evidence + accepted."""
    obs_id = world.record_observation(ObservationData(
        subject="orders-api", predicate="exposes", object="POST /orders",
        evidence=EvidenceData(tool="semgrep", rule="spring.endpoint",
                              file="src/Orders.kt", start_line=10,
                              end_line=18)))
    ev_id = world.record_evidence(EvidenceData(
        tool="ast-grep", rule="route-decorator", file="src/routes.ts",
        start_line=3, end_line=9))
    claim_id = world.propose_derived_claim(
        ClaimData(statement="orders-api exposes POST /orders",
                  subjects=["Orders API"], evidence_refs=[ev_id]),
        obs_id)
    world.accept_claim(claim_id)
    el_id = world.add_architecture_element("Orders API", "container")
    other_id = world.add_architecture_element("Billing", "component")
    world.add_architecture_relation("exposes", el_id, other_id)
    return {"obs": obs_id, "evidence": ev_id, "claim": claim_id,
            "element": el_id}


class TestPortConformance:
    def test_world_satisfies_query_and_governance_ports(self, world):
        assert isinstance(world, ArchitectureQueryPort)
        assert isinstance(world, GovernancePort)


class TestGetStatus:
    def test_healthy_world_has_no_suggestions(self, world, populated):
        result = get_status(world, code_index=_FakeIndex())
        assert result.suggestions == []
        assert result.snapshot.knowledge.elements == 2
        assert result.snapshot.knowledge.relations == 1
        assert result.schema == STATUS_SCHEMA

    def test_missing_index_suggests_discover(self, world, populated):
        result = get_status(world)
        reasons = [s.reason_code for s in result.suggestions]
        assert "INDEX_MISSING" in reasons

    def test_dirty_repo_suggests_stale_index(self, world, populated, repo):
        (repo / "scratch.txt").write_text("dirty\n")
        result = get_status(world, code_index=_FakeIndex())
        reasons = [s.reason_code for s in result.suggestions]
        assert "INDEX_STALE" in reasons

    def test_empty_world_suggests_discover(self, world):
        result = get_status(world, code_index=_FakeIndex())
        reasons = [s.reason_code for s in result.suggestions]
        assert "WORLD_EMPTY" in reasons

    def test_suggestions_are_typed_actions(self, world):
        result = get_status(world)
        s = result.suggestions[0]
        assert isinstance(s, ActionSuggestion)
        assert s.mutation_scope == "workspace"
        assert s.risk == "low"
        assert s.preconditions == ["project_initialized"]

    def test_status_is_deterministic(self, world, populated):
        r1 = get_status(world, code_index=_FakeIndex())
        r2 = get_status(world, code_index=_FakeIndex())
        assert r1.model_dump() == r2.model_dump()
        assert snapshot_digest(r1.snapshot) == snapshot_digest(r2.snapshot)

    def test_result_forbids_extra_fields(self, world):
        with pytest.raises(ValidationError):
            StatusResult(**{**get_status(world).model_dump(),
                            "extra": True})


class TestExplain:
    def test_claim_lineage(self, world, populated):
        exp = explain(world, populated["claim"])
        assert exp.subject_type == "claim"
        assert len(exp.observations) == 1
        assert exp.observations[0]["id"] == populated["obs"]
        assert any(e["id"] == populated["evidence"] for e in exp.evidence)
        assert exp.claims[0]["status"] == "accepted"
        assert exp.claims[0]["contradicted"] is False
        assert exp.gaps == []

    def test_element_lineage_and_declared_gap(self, world, populated):
        exp = explain(world, "Orders API")
        assert exp.subject_type == "architecture_element"
        assert len(exp.relations) == 1
        assert exp.relations[0]["kind"] == "exposes"
        # claim subjects include "Orders API" → lineage found
        assert exp.claims and exp.gaps == []
        # an element no claim mentions declares the gap instead of hiding it
        gap_exp = explain(world, "Billing")
        assert gap_exp.gaps == ["element has no claim lineage recorded"]

    def test_observation_finds_claiming_chain(self, world, populated):
        exp = explain(world, "orders-api")
        assert exp.subject_type == "observation"
        assert exp.claims[0]["id"] == populated["claim"]
        assert exp.evidence, "embedded evidence is surfaced"

    def test_evidence_by_id(self, world, populated):
        exp = explain(world, populated["evidence"])
        assert exp.subject_type == "evidence"
        assert exp.claims[0]["id"] == populated["claim"]

    def test_relation_by_id(self, world, populated):
        relations = world.architecture_relations()
        assert relations, "populated world has one exposes relation"
        rel = relations[0]
        exp = explain(world, rel["id"])
        assert exp.subject_type == "architecture_relation"
        assert exp.subject_id == rel["id"]
        assert "Orders API" in exp.title and "Billing" in exp.title
        assert exp.title == "Orders API -[exposes]-> Billing"
        assert exp.relations[0]["kind"] == "exposes"
        assert exp.gaps == ["relation has no claim lineage recorded"]

    def test_unknown_subject_raises_stable_code(self, world):
        with pytest.raises(SubjectNotFound) as exc:
            explain(world, "no-such-thing")
        assert exc.value.code == "SUBJECT_NOT_FOUND"

    def test_explanation_contract(self, world, populated):
        exp = explain(world, populated["claim"])
        assert isinstance(exp, Explanation)
        assert exp.schema == "arch-skillkit/explanation-v1"
        with pytest.raises(ValidationError):
            Explanation(**{**exp.model_dump(), "unexpected": 1})


class TestGovernancePort:
    def test_reads_reflect_world(self, world, populated):
        assert world.proposals() == []
        world.policies.record_rule(
            "no-ui-to-domain", "UI must not import domain",
            forbidden_relation="imports",
            source_category="ui", target_category="domain")
        rules = world.architecture_rules()
        assert len(rules) == 1
        assert rules[0]["data"]["name"] == "no-ui-to-domain"
        assert world.findings() == []
