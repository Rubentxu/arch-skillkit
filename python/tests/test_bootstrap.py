"""Agent bootstrap context (V2.4 M2 final deliverable, docs/v2/58).

One deterministic call assembles the agent's starting state: lease +
status + budgeted pack + open gaps. The world event log stays
untouched.
"""

import subprocess

import pytest

from archskillkit.application.queries.bootstrap import (
    BOOTSTRAP_SCHEMA,
    bootstrap_agent,
)
from archskillkit.application.queries.context_query import ContextQuery
from archskillkit.codeindex import CodeIndex
from archskillkit.context import Budget
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
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "runtime"))
    return data


@pytest.fixture()
def repo(tmp_path):
    repo = tmp_path / "fixture"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "orders.py").write_text("class OrdersAPI:\n    pass\n")
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
    ev = world.record_evidence(EvidenceData(
        tool="semgrep", rule="r", file="src/orders.py", start_line=1))
    a = world.add_architecture_element("Orders API", "container")
    b = world.add_architecture_element("Billing", "component")
    world.add_architecture_relation("exposes", a, b,
                                    data={"evidence_ids": [ev]})
    world.record_knowledge_gap("who owns billing?", impact="medium")
    yield world
    world.close()


class TestAgentBootstrap:
    def test_assembles_coherent_starting_state(self, world):
        boot = bootstrap_agent(world)
        assert boot.schema == BOOTSTRAP_SCHEMA
        assert boot.snapshot.snapshot_id.startswith("snap-")
        assert boot.session.status == "ACTIVE"
        assert boot.session.snapshot_id == boot.snapshot.snapshot_id
        assert boot.context_pack.goal.startswith("project overview")
        assert any(s.reason_code == "INDEX_MISSING"
                   for s in boot.suggestions)
        assert len(boot.open_gaps) == 1

    def test_custom_query_and_index(self, world):
        index = CodeIndex(world.workspace / "code.sqlite").open()
        try:
            custom = bootstrap_agent(
                world, index,
                query=ContextQuery(goal="orders api", subject="Orders API",
                                   budget=Budget(max_nodes=1)))
        finally:
            index.close()
        assert custom.context_pack.goal == "orders api"
        assert len(custom.context_pack.architecture["elements"]) == 1

    def test_suggestions_reflect_state(self, world):
        boot = bootstrap_agent(world)
        # no code index open -> INDEX_MISSING expected
        assert any(s.reason_code == "INDEX_MISSING"
                   for s in boot.suggestions)

    def test_world_event_log_untouched(self, world):
        before = len(world.graph.events)
        bootstrap_agent(world)
        bootstrap_agent(world)
        assert len(world.graph.events) == before

    def test_extra_fields_forbidden(self, world):
        from pydantic import ValidationError
        boot = bootstrap_agent(world)
        with pytest.raises(ValidationError):
            type(boot)(**{**boot.model_dump(), "extra": 1})
