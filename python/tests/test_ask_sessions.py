"""ark ask (NL → typed intent equivalence) + AgentSession leases
(V2.4 M2, docs/v2/59 gates).

M2 gates under test: ask NL and typed inputs produce equivalent intent
on fixtures; AgentSession stale detection marks leases whose revisions
moved; sessions never touch the world event log.
"""

import subprocess
from pathlib import Path

import pytest
import yaml
from jsonschema import validate as js_validate

from archskillkit.application.queries.agent_session import (
    open_agent_session,
    session_is_current,
)
from archskillkit.application.queries.analyze_impact import analyze_impact
from archskillkit.application.queries.ask import ask, parse_ask
from archskillkit.application.queries.context_query import (
    ContextQuery,
    compile_context,
)
from archskillkit.codeindex import CodeIndex
from archskillkit.context import ContextCompiler
from archskillkit.packs.arch_core import EvidenceData
from archskillkit.runtime_state.agent_sessions import (
    AgentSession,
    AgentSessionStore,
)
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
    return tmp_path


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


@pytest.fixture()
def world(sandbox, repo):
    world = ArchitectureWorld.for_repo(repo).open()
    world.ensure_project()
    ev = world.record_evidence(EvidenceData(
        tool="semgrep", rule="spring.endpoint", file="src/orders.py",
        start_line=1))
    a = world.add_architecture_element("Orders API", "container")
    b = world.add_architecture_element("Billing", "component")
    world.add_architecture_relation("exposes", a, b,
                                    data={"evidence_ids": [ev]})
    yield world
    world.close()


@pytest.fixture()
def index(world):
    index = CodeIndex(world.workspace / "code.sqlite").open()
    yield index
    index.close()


class TestParseAsk:
    def test_impact_triggers_route_to_impact(self):
        for question in ("what breaks if src/orders.py changes?",
                         "impact of changing Orders API",
                         "if we change src/orders.py"):
            intent = parse_ask(question)
            assert intent.action == "impact", question
            assert intent.context is None

    def test_file_vs_symbol_classification(self):
        assert parse_ask("impact of changing src/orders.py") \
            .impact_kind == "file"
        assert parse_ask("what breaks if OrdersAPI?") \
            .impact_kind == "symbol"

    def test_impact_value_is_clean(self):
        intent = parse_ask("What breaks if I change src/orders.py?")
        assert intent.impact_value == "src/orders.py"

    def test_other_questions_compile_context(self):
        intent = parse_ask("how is the orders api structured?")
        assert intent.action == "context"
        assert intent.context == ContextQuery(
            goal="how is the orders api structured?")


class TestAskEquivalence:
    def test_ask_impact_matches_typed_impact(self, world, index):
        _, via_ask = ask(world, index,
                         "what breaks if src/orders.py changes?")
        typed = analyze_impact(world, index, "file", "src/orders.py")
        assert via_ask.model_dump() == typed.model_dump()

    def test_ask_context_matches_typed_query(self, world, index):
        _, via_ask = ask(world, index, "orders api")
        typed = compile_context(
            ContextCompiler(world, index),
            ContextQuery(goal="orders api"))
        assert via_ask.model_dump() == typed.model_dump()

    def test_ask_is_deterministic(self, world, index):
        first = ask(world, index, "what breaks if src/orders.py changes?")
        again = ask(world, index, "what breaks if src/orders.py changes?")
        assert first[1].model_dump() == again[1].model_dump()


class TestAgentSession:
    def test_open_lease_binds_current_revisions(self, world, index):
        session = open_agent_session(world, index,
                                     scope={"elements": ["Orders API"]},
                                     budget={"max_estimated_tokens": 4000})
        assert session.status == "ACTIVE"
        assert session.snapshot_id.startswith("snap-")
        assert session.world_revision == world.last_event_id()
        assert session.scope == {"elements": ["Orders API"]}
        assert session.budget == {"max_estimated_tokens": 4000}

    def test_stale_detection_after_world_moves(self, world, index):
        store = AgentSessionStore()
        session = open_agent_session(world, index, store=store)
        assert store.list(status="ACTIVE")[0].session_id == \
            session.session_id

        world.add_architecture_element("New Thing", "component")
        snapshot_dirty = None
        from archskillkit.application.snapshot_builder import build_snapshot
        snapshot_dirty = build_snapshot(world, index)
        staled = store.detect_stale(snapshot_dirty)
        assert [s.session_id for s in staled] == [session.session_id]
        assert store.get(session.session_id).status == "STALE"

    def test_session_is_current_round_trip(self, world, index):
        session = open_agent_session(world, index)
        assert session_is_current(session, world, index) is True
        world.add_architecture_element("Another", "component")
        assert session_is_current(session, world, index) is False

    def test_closed_sessions_never_go_stale(self, world, index):
        store = AgentSessionStore()
        session = open_agent_session(world, index, store=store)
        store.close(session.session_id)
        from archskillkit.application.snapshot_builder import build_snapshot
        store.detect_stale(build_snapshot(world, index))
        assert store.get(session.session_id).status == "CLOSED"

    def test_stale_detection_after_code_generation_changes(self, world, index):
        """Session goes stale when code_generation differs from the leased one."""
        store = AgentSessionStore()
        from archskillkit.application.snapshot_builder import build_snapshot
        session = open_agent_session(world, index, store=store)
        # Lease a fresh snapshot
        snap_before = build_snapshot(world, index)
        assert session.code_generation == snap_before.code_revision.generation
        # Simulate a new scan by bumping the generation in the session
        # (without actually re-scanning — tests the is_current logic directly)
        bumped = session.model_copy(
            update={"code_generation": "gen-999-fake-scan"})
        store._mutate(lambda s: {**s, session.session_id: bumped})
        snap_after = build_snapshot(world, index)
        staled = store.detect_stale(snap_after)
        assert any(s.session_id == session.session_id for s in staled)
        assert store.get(session.session_id).status == "STALE"

    def test_stale_detection_all_three_dimensions(self, world, index):
        """Session is stale when ANY of world/code/policy revision diverges."""
        store = AgentSessionStore()
        session = open_agent_session(world, index, store=store)
        from archskillkit.application.snapshot_builder import build_snapshot
        snap = build_snapshot(world, index)
        # All three are current initially
        assert session.is_current(snap) is True
        # world_revision diverges
        bad_world = session.model_copy(
            update={"world_revision": "event-never-existed"})
        assert bad_world.is_current(snap) is False
        # code_generation diverges
        bad_code = session.model_copy(
            update={"code_generation": "gen-000"})
        assert bad_code.is_current(snap) is False
        # policy_revision diverges
        bad_policy = session.model_copy(
            update={"policy_revision": "policy-000"})
        assert bad_policy.is_current(snap) is False

    def test_sessions_persist_across_store_instances(self, sandbox, world,
                                                     index):
        store = AgentSessionStore()
        session = open_agent_session(world, index, store=store)
        assert AgentSessionStore().get(session.session_id) is not None

    def test_session_matches_design_schema(self, world, index):
        schema = yaml.safe_load(
            (Path(__file__).resolve().parents[2]
             / "design/schemas/v2.4/agent-session.yaml").read_text())
        session = open_agent_session(world, index,
                                     scope={"k": "v"},
                                     budget={"max_estimated_tokens": 100})
        js_validate(session.model_dump(), schema)

    def test_session_extra_fields_forbidden(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            AgentSession(session_id="s", snapshot_id="snap-x",
                         world_revision="evt_001", code_generation="g",
                         policy_revision="none", surprise=1)

    def test_sessions_live_outside_the_world(self, world, index):
        before = len(world.graph.events)
        open_agent_session(world, index)
        AgentSessionStore().list()
        assert len(world.graph.events) == before
