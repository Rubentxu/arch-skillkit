"""V2 Phase D — Context Compiler (M2-D1..D4, docs/v2/06).

Compiles budgeted ContextPacks from the Architecture World + Code Index
instead of handing agents the whole graph. Invariants under test:
UAT2-007 (budgets on nodes/edges/source lines are respected),
UAT2-008 (source is only opened from resolved locations) and
determinism (same inputs → identical pack).
"""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from archskillkit.codeindex import CodeIndex
from archskillkit.context import Budget, ContextCompiler, classify_intent
from archskillkit.promotion import discover
from archskillkit.world import ArchitectureWorld

HTTP_KT = "kotlin-spring/src/main/kotlin/demo/infra/Http.kt"


def _element(elem_id: str, name: str) -> dict:
    return {"id": elem_id, "data": {"name": name, "kind": "component",
                                    "origin": "DETECTED", "confidence": "high"}}


def _outline(name: str, file: str, root: Path) -> dict:
    return {"ruleId": "outline.kt.class", "text": name,
            "file": str(root / file),
            "range": {"start": {"line": 0, "column": 0},
                      "end": {"line": 0, "column": 10}},
            "lines": f"{name}()", "language": "Kotlin",
            "metaVariables": {"single": {}, "multi": {}}}


def _semgrep(path: str, line: int) -> dict:
    return {"check_id": "spring.endpoint", "path": path,
            "start": {"line": line, "col": 1}, "end": {"line": line, "col": 30},
            "extra": {"message": "m", "metavars": {}, "lines": "x"}}


@pytest.fixture()
def promoted_world(kotlin_world_index):
    world, index = kotlin_world_index
    discover(world, index, scan_run_id="scan-1")
    return world, index


@pytest.fixture()
def repo_with_source(promoted_world):
    """The analyzed repository actually containing the scanned source so
    snippets can be resolved."""
    world, index = promoted_world
    src = Path(world.root) / HTTP_KT
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("".join(f"// line {i}\n" for i in range(1, 41)))
    return world, index


class TestContextPackSchema:
    def test_budget_defaults_follow_design_schema(self):
        budget = Budget()
        assert budget.max_nodes == 50
        assert budget.max_edges == 100
        assert budget.max_source_lines == 200

    def test_negative_budget_rejected(self):
        with pytest.raises(ValidationError):
            Budget(max_nodes=-1)

    def test_intent_classification_is_deterministic(self):
        assert classify_intent("list the http endpoints of orders") == "endpoints"
        assert classify_intent("show drift against boundary rules") == "drift"
        assert classify_intent("what evidence supports this claim?") == "evidence"
        assert classify_intent("give me an overview") == "overview"
        assert classify_intent("give me an overview") == "overview"  # stable


class TestOverviewCompile:
    def test_pack_contains_full_architecture(self, promoted_world):
        world, index = promoted_world
        pack = ContextCompiler(world, index).compile(goal="overview")
        assert len(pack.architecture["elements"]) == 10
        assert len(pack.architecture["relations"]) == 5
        assert pack.summary
        assert pack.schema_version == 1

    def test_metrics_recorded(self, promoted_world):
        world, index = promoted_world
        pack = ContextCompiler(world, index).compile(goal="overview")
        m = pack.metrics
        assert m["elements"] == 10
        assert m["relations"] == 5
        assert m["context_reads"] >= 1
        assert m["compiler_calls"] == m["context_reads"]
        assert m["source_file_reads"] == 0
        assert m["source_bytes_read"] == 0

    def test_empty_world_compiles_minimal_pack(self, repo):
        from archskillkit.codeindex import CodeIndex
        world = __import__("archskillkit.world", fromlist=["ArchitectureWorld"]) \
            .ArchitectureWorld.for_repo(repo).open()
        index = CodeIndex(world.workspace / "code.sqlite").open()
        pack = ContextCompiler(world, index).compile(goal="anything")
        assert pack.architecture == {"elements": [], "relations": []}
        assert pack.uncertainties == []
        world.close()
        index.close()


class TestSubjectResolution:
    def test_subject_narrows_the_pack(self, promoted_world):
        world, index = promoted_world
        pack = ContextCompiler(world, index).compile(
            goal="how does payment exposure work", subject="getPayment")
        names = {el["name"] for el in pack.architecture["elements"]}
        assert "endpoint@11" in names
        assert all("PaymentRepository" not in n for n in names)
        assert pack.architecture["relations"]

    def test_subject_resolves_through_code_index(self, promoted_world):
        world, index = promoted_world
        pack = ContextCompiler(world, index).compile(
            goal="overview", subject="findById")
        # no architecture element for findById: falls back to code facts
        assert pack.code["symbols"], "expected code symbols for findById"
        assert all("findById" in s["name"] for s in pack.code["symbols"])

    def test_unknown_subject_records_uncertainty(self, promoted_world):
        world, index = promoted_world
        pack = ContextCompiler(world, index).compile(
            goal="overview", subject="does-not-exist")
        assert pack.uncertainties
        assert pack.architecture["elements"] == []


class TestBudgets:
    def test_node_budget_respected(self, promoted_world):
        world, index = promoted_world
        pack = ContextCompiler(world, index).compile(
            goal="overview", budget=Budget(max_nodes=3))
        assert len(pack.architecture["elements"]) <= 3

    def test_edge_budget_respected(self, promoted_world):
        world, index = promoted_world
        pack = ContextCompiler(world, index).compile(
            goal="overview", budget=Budget(max_edges=2))
        assert len(pack.architecture["relations"]) <= 2

    def test_source_line_budget_respected(self, repo_with_source):
        world, index = repo_with_source
        pack = ContextCompiler(world, index).compile(
            goal="show me the endpoint handler", subject="getPayment",
            budget=Budget(max_source_lines=4))
        total = sum(s["end_line"] - s["start_line"] + 1
                    for s in pack.source_snippets)
        assert 0 < total <= 4

    def test_edges_only_reference_kept_nodes(self, promoted_world):
        world, index = promoted_world
        pack = ContextCompiler(world, index).compile(
            goal="overview", budget=Budget(max_nodes=2, max_edges=100))
        kept = {el["id"] for el in pack.architecture["elements"]}
        for rel in pack.architecture["relations"]:
            assert rel["source"] in kept and rel["target"] in kept


class TestSnippets:
    def test_source_metrics_count_successful_file_reads(self, repo_with_source):
        world, index = repo_with_source
        compiler = ContextCompiler(world, index)

        first = compiler.compile(
            goal="show me the endpoint handler", subject="getPayment")
        second = compiler.compile(
            goal="show me the endpoint handler", subject="getPayment")

        assert first.metrics["compiler_calls"] == 1
        assert first.metrics["source_file_reads"] == len(first.source_snippets)
        assert first.metrics["source_bytes_read"] > 0
        assert second.metrics["compiler_calls"] == 2
        assert second.metrics["source_file_reads"] == (
            2 * len(first.source_snippets))
        assert second.metrics["context_reads"] == second.metrics["compiler_calls"]

    def test_snippet_read_from_resolved_location(self, repo_with_source):
        world, index = repo_with_source
        pack = ContextCompiler(world, index).compile(
            goal="show me the endpoint handler", subject="getPayment")
        assert pack.source_snippets
        snippet = pack.source_snippets[0]
        assert snippet["path"] == HTTP_KT
        assert snippet["start_line"] >= 1
        assert "line 12" in snippet["text"]  # getPayment is declared at line 12

    def test_source_only_opened_from_index_locations(self, repo_with_source):
        # UAT2-008: every snippet path must come from a code index location
        world, index = repo_with_source
        indexed_paths = {row["path"] for row in index.search_symbol("getPayment")}
        pack = ContextCompiler(world, index).compile(
            goal="show me the endpoint handler", subject="getPayment")
        assert indexed_paths
        for snippet in pack.source_snippets:
            assert any(sp.endswith(snippet["path"]) or snippet["path"] == sp
                       for sp in indexed_paths)

    def test_missing_source_degrades_to_uncertainty(self, promoted_world):
        # same world/index but the repository has no real files
        world, index = promoted_world
        pack = ContextCompiler(world, index).compile(
            goal="show me the endpoint handler", subject="getPayment")
        assert pack.source_snippets == []
        assert any("source" in u.lower() for u in pack.uncertainties)


class TestDeterminism:
    def test_same_inputs_same_pack(self, repo_with_source):
        world, index = repo_with_source
        compiler = ContextCompiler(world, index)
        first = compiler.compile(goal="overview", subject="getPayment")
        second = compiler.compile(goal="overview", subject="getPayment")
        # I/O counters are instance-scoped by design; everything else is stable.
        for metric in ("compiler_calls", "context_reads", "source_file_reads",
                       "source_bytes_read"):
            first.metrics.pop(metric)
            second.metrics.pop(metric)
        assert first.model_dump() == second.model_dump()

    def test_compilation_does_not_mutate_the_world(self, repo_with_source):
        world, index = repo_with_source
        before = world.snapshot()
        ContextCompiler(world, index).compile(goal="overview")
        ContextCompiler(world, index).compile(goal="drift status")
        assert world.snapshot() == before

    def test_pack_serializes_to_json(self, repo_with_source):
        world, index = repo_with_source
        pack = ContextCompiler(world, index).compile(goal="overview")
        assert json.loads(pack.model_dump_json())["goal"] == "overview"


class TestRelevanceSignals:
    """Recent graph delta + changed-file proximity (docs/v2/46,
    camino siguiente) — the remaining review P2 ranking inputs."""

    def test_recent_delta_name_boosts_element(self):
        elements = [_element("a", "OrderService"), _element("b", "LegacyBatch")]
        ranked = ContextCompiler._ranked(
            elements, seeds=set(), goal="", relations=[],
            recent_names=frozenset({"orderservice"}))
        assert ranked[0]["data"]["name"] == "OrderService"

    def test_changed_file_proximity_boosts_element(self):
        elements = [_element("a", "OrderService"), _element("b", "LegacyBatch")]
        ranked = ContextCompiler._ranked(
            elements, seeds=set(), goal="", relations=[],
            changed_files=frozenset({"src/OrderService.kt"}),
            evidence_files={"a": frozenset({"src/OrderService.kt"})})
        assert ranked[0]["data"]["name"] == "OrderService"

    def test_without_signals_name_tiebreak_holds(self):
        elements = [_element("a", "Beta"), _element("b", "Alpha")]
        ranked = ContextCompiler._ranked(elements, seeds=set(), goal="",
                                         relations=[])
        assert [e["id"] for e in ranked] == ["b", "a"]

    def test_delta_beats_partial_goal_match_but_not_exact(self):
        ranked = ContextCompiler._ranked(
            [_element("a", "OrderService"), _element("b", "PaymentGateway"),
             _element("c", "Payment")],
            seeds=set(), goal="payment", relations=[],
            recent_names=frozenset({"orderservice"}))
        assert [e["id"] for e in ranked] == ["c", "a", "b"]

    def test_compile_ranks_recent_delta_element_first(self, repo):
        world = ArchitectureWorld.for_repo(repo).open()
        world.ensure_project()
        index = CodeIndex(world.workspace / "code.sqlite").open()
        try:
            world.add_architecture_element("Alpha", "component",
                                           "DETECTED", "high")
            world.add_architecture_element("Gamma", "component",
                                           "DETECTED", "high")
            gen1 = json.dumps(_outline("Alpha", "a.kt", repo)) + "\n"
            index.ingest_astgrep(gen1, scan_run_id="g1", scan_root=repo)
            compiler = ContextCompiler(world, index, source_root=repo)
            first = compiler.compile(goal="overview")
            assert [e["name"] for e in first.architecture["elements"]] == \
                ["Alpha", "Gamma"]  # tiebreak: alphabetical

            gen2 = "\n".join(json.dumps(r) for r in (
                _outline("Alpha", "a.kt", repo),
                _outline("Gamma", "c.kt", repo))) + "\n"
            index.ingest_astgrep(gen2, scan_run_id="g2", scan_root=repo)
            index.ingest_semgrep(json.dumps({"results": [
                _semgrep(str(repo / "c.kt"), 1)]}),
                scan_run_id="g2", scan_root=repo)
            second = compiler.compile(goal="overview")
            assert [e["name"] for e in second.architecture["elements"]] == \
                ["Gamma", "Alpha"]  # recent graph delta boost
        finally:
            index.close()
            world.close()
