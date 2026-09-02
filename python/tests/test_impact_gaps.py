"""AnalyzeImpact + KnowledgeGap persistence (V2.4 M2, docs/v2/67
slice 7).

Gates: impact over file/symbol/element; gaps persisted in the world
event log (auditable via replay) with status transitions; analysis and
gap reads never mutate the world.
"""

import subprocess

import pytest
import yaml
from jsonschema import validate as js_validate
from pydantic import ValidationError

from archskillkit.application.queries.analyze_impact import (
    IMPACT_SCHEMA,
    ImpactResult,
    analyze_impact,
)
from archskillkit.codeindex import CodeIndex
from archskillkit.packs.arch_core import EvidenceData
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
    (repo / "src" / "orders.py").write_text(
        "class OrdersAPI:\n    def expose(self):\n        pass\n")
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")
    return repo


def _populate(world):
    ev = world.record_evidence(EvidenceData(
        tool="semgrep", rule="spring.endpoint", file="src/orders.py",
        start_line=1))
    a = world.add_architecture_element("Orders API", "container")
    b = world.add_architecture_element("Billing", "component")
    world.add_architecture_relation("exposes", a, b,
                                    data={"evidence_ids": [ev]})
    return a, b, ev


@pytest.fixture()
def world(sandbox, repo):
    world = ArchitectureWorld.for_repo(repo).open()
    world.ensure_project()
    _populate(world)
    yield world
    world.close()


@pytest.fixture()
def index(world):
    index = CodeIndex(world.workspace / "code.sqlite").open()
    yield index
    index.close()


class TestImpactResult:
    def test_result_contract(self):
        result = ImpactResult(kind="file", value="x.py")
        assert result.schema == IMPACT_SCHEMA
        with pytest.raises(ValidationError):
            ImpactResult(kind="repo", value="x")
        with pytest.raises(ValidationError):
            ImpactResult(kind="file", value="x", extra=1)


class TestImpactByKind:
    def test_file_impact_finds_elements_relations_and_evidence(
            self, world, index):
        result = analyze_impact(world, index, "file", "src/orders.py")
        assert result.resolved is True
        names = {e["name"] for e in result.elements}
        assert {"Orders API", "Billing"} <= names
        assert len(result.relations) == 1
        assert len(result.evidence) == 1
        assert result.paths == ["src/orders.py"]

    def test_file_not_in_index_declares_gap(self, world, index):
        result = analyze_impact(world, index, "file", "src/nope.py")
        assert result.resolved is False
        assert result.gaps == ["file not in code index: src/nope.py"]

    def test_symbol_impact_via_element_name(self, world, index):
        result = analyze_impact(world, index, "symbol", "Orders")
        assert result.resolved is True
        assert any(e["name"] == "Orders API" for e in result.elements)
        assert result.relations

    def test_symbol_unknown_still_reports(self, world, index):
        result = analyze_impact(world, index, "symbol", "ghost_symbol")
        assert result.resolved is False
        assert result.gaps

    def test_element_impact_by_name_one_hop(self, world, index):
        result = analyze_impact(world, index, "element", "Orders API")
        assert result.resolved is True
        assert len(result.relations) == 1
        assert {e["name"] for e in result.elements} == \
            {"Orders API", "Billing"}

    def test_element_unknown_declares_gap(self, world, index):
        result = analyze_impact(world, index, "element", "Ghost")
        assert result.resolved is False
        assert result.gaps == ["no architecture element matches: Ghost"]


class TestKnowledgeGap:
    def test_record_dedups_open_questions(self, world):
        first = world.record_knowledge_gap(
            "who owns billing?", impact="high",
            related_refs=["src/billing.py"])
        second = world.record_knowledge_gap("who owns billing?")
        assert first == second
        assert len(world.knowledge_gaps()) == 1
        gap = world.get_object(first)
        assert gap["data"]["impact"] == "high"
        assert gap["data"]["status"] == "OPEN"

    def test_status_transitions_and_filters(self, world):
        gap_id = world.record_knowledge_gap("what backs this relation?")
        world.set_knowledge_gap_status(gap_id, "INVESTIGATING")
        assert world.knowledge_gaps(status="OPEN") == []
        assert len(world.knowledge_gaps(status="INVESTIGATING")) == 1
        world.set_knowledge_gap_status(gap_id, "RESOLVED")
        assert world.knowledge_gaps(status="RESOLVED")[0]["id"] == gap_id

    def test_set_status_rejects_non_gap(self, world):
        from archskillkit.errors import PromotionError
        element_id = world.find_objects("architecture_element")[0]["id"]
        with pytest.raises(PromotionError):
            world.set_knowledge_gap_status(element_id, "RESOLVED")

    def test_gaps_survive_replay(self, sandbox, repo):
        world = ArchitectureWorld.for_repo(repo).open()
        world.ensure_project()
        gap_id = world.record_knowledge_gap(
            "is the orders boundary enforced?", impact="high",
            evidence_needed=["boundary rule test"])
        report = world.replay_verify()
        world.close()

        reopened = ArchitectureWorld.for_repo(repo).open()
        gaps = reopened.knowledge_gaps()
        reopened.close()
        assert report.ok is True
        assert len(gaps) == 1
        assert gaps[0]["id"] == gap_id
        assert gaps[0]["data"]["evidence_needed"] == \
            ["boundary rule test"]

    def test_gap_matches_design_schema(self, world):
        from pathlib import Path
        schema = yaml.safe_load(
            (Path(__file__).resolve().parents[2]
             / "design/schemas/v2.4/knowledge-gap.yaml").read_text())
        world.record_knowledge_gap("schema check?", related_refs=["r"])
        gap = world.knowledge_gaps()[0]
        instance = {"id": gap["id"], **gap["data"]}
        js_validate(instance, schema)
