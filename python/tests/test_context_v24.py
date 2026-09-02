"""Typed ContextQuery + Context KPIs (V2.4 M2, docs/v2/56, slice 6).

Gates: typed query is the single compile contract; pack-level KPIs
(bytes/tokens estimate/evidence density) are deterministic and honest.
"""

import json
import subprocess

import pytest
from pydantic import ValidationError

from archskillkit.application.queries.context_query import (
    CONTEXT_QUERY_SCHEMA,
    ContextQuery,
    compile_context,
)
from archskillkit.codeindex import CodeIndex
from archskillkit.context import Budget, ContextCompiler
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
    (repo / "src" / "main.rs").write_text("fn main() {}\n")
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")
    return repo


@pytest.fixture()
def world(sandbox, repo):
    world = ArchitectureWorld.for_repo(repo).open()
    world.ensure_project()
    yield world
    world.close()


@pytest.fixture()
def populated_world(world):
    ev = world.record_evidence(EvidenceData(
        tool="semgrep", rule="spring.endpoint", file="src/Orders.kt",
        start_line=10))
    a = world.add_architecture_element("Orders API", "container")
    b = world.add_architecture_element("Billing", "component")
    world.add_architecture_relation("exposes", a, b,
                                    data={"evidence_ids": [ev]})
    return world


@pytest.fixture()
def index(world):
    index = CodeIndex(world.workspace / "code.sqlite").open()
    yield index
    index.close()


def _query(goal="orders", **kw) -> ContextQuery:
    defaults: dict = {"goal": goal}
    defaults.update(kw)
    return ContextQuery(**defaults)


class TestContextQueryContract:
    def test_schema_and_defaults(self):
        q = _query()
        assert q.schema == CONTEXT_QUERY_SCHEMA
        assert q.subject is None
        assert q.budget == Budget()

    def test_goal_required_and_extra_forbidden(self):
        with pytest.raises(ValidationError):
            ContextQuery()
        with pytest.raises(ValidationError):
            _query(unexpected=True)

    def test_budget_respected(self, populated_world, index):
        query = _query(budget=Budget(max_nodes=1, max_edges=0,
                                     max_source_lines=0))
        pack = compile_context(ContextCompiler(populated_world, index),
                               query)
        assert len(pack.architecture["elements"]) == 1
        assert pack.architecture["relations"] == []


class TestTypedEquivalence:
    def test_typed_query_matches_kwargs_compile(self, populated_world,
                                                index):
        typed = compile_context(
            ContextCompiler(populated_world, index),
            _query(goal="orders api", subject="Orders API"))
        legacy = ContextCompiler(populated_world, index).compile(
            goal="orders api", subject="Orders API",
            budget=Budget())
        assert typed.model_dump() == legacy.model_dump()

    def test_json_round_trip_preserves_intent(self, populated_world,
                                              index):
        query = ContextQuery(**json.loads(_query(
            goal="orders api", subject="Orders API").model_dump_json()))
        first = compile_context(ContextCompiler(populated_world, index),
                                query)
        again = compile_context(ContextCompiler(populated_world, index),
                                ContextQuery(**query.model_dump()))
        assert first.model_dump() == again.model_dump()


class TestContextKpis:
    def test_pack_bytes_and_tokens_are_deterministic(self, populated_world,
                                                     index):
        compiler = ContextCompiler(populated_world, index)
        pack = compile_context(compiler, _query())
        expected_bytes = len(pack.model_dump_json(exclude={"metrics"}))
        assert pack.metrics["pack_bytes"] == expected_bytes
        assert pack.metrics["pack_tokens"] == expected_bytes // 4
        again = compile_context(ContextCompiler(populated_world, index),
                                _query())
        assert again.metrics["pack_bytes"] == expected_bytes

    def test_evidence_density_one_when_all_relations_backed(
            self, populated_world, index):
        pack = compile_context(ContextCompiler(populated_world, index),
                               _query())
        assert pack.metrics["evidence_density"] == 1.0
        assert len(pack.architecture["relations"]) == 1

    def test_evidence_density_zero_without_relations(self, world, index):
        world.add_architecture_element("Solo", "component")
        pack = compile_context(ContextCompiler(world, index), _query())
        assert pack.metrics["evidence_density"] == 0.0

    def test_density_between_zero_and_one(self, world, index):
        ev = world.record_evidence(EvidenceData(
            tool="semgrep", rule="r", file="f.kt", start_line=1))
        a = world.add_architecture_element("A", "container")
        b = world.add_architecture_element("B", "component")
        c = world.add_architecture_element("C", "component")
        world.add_architecture_relation("exposes", a, b,
                                        data={"evidence_ids": [ev]})
        world.add_architecture_relation("consumes", b, c)
        pack = compile_context(ContextCompiler(world, index), _query())
        assert pack.metrics["evidence_density"] == pytest.approx(0.5)
