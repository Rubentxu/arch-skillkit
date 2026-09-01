"""Property tests PR-1..PR-5 (docs/v2/45 §3, V2.3-F1).

Each test pins one domain invariant that earlier regressions violated.
Deterministic: hypothesis-based generation arrives in V2.3-F8.
"""

import json

import pytest
from conftest import KOTLIN_RUN
from test_promotion import inferred_observation

from archskillkit.codeindex import CodeIndex
from archskillkit.projections.adapters.likec4 import LikeC4Adapter
from archskillkit.projections.writer import ProjectionError, project_to_workspace
from archskillkit.promotion import discover, evaluate_claims, propose_claims
from archskillkit.proposals import promote, structural_diff


def _astgrep_ndjson(*records: tuple[str, str, str, int]) -> str:
    """(file, rule_id, text, line) records as ast-grep --json=stream NDJSON."""
    lines = []
    for file_path, rule_id, text, line in records:
        lines.append(json.dumps({
            "file": file_path, "ruleId": rule_id, "text": text,
            "range": {"start": {"line": line - 1}},
            "lines": text,
        }))
    return "\n".join(lines)


def _semgrep_json(*results: tuple[str, str, int, str]) -> str:
    """(path, check_id, line, literal) results as semgrep --json."""
    return json.dumps({"results": [
        {"check_id": check_id, "path": path,
         "start": {"line": line},
         "extra": {"metavars": {"$X": {"abstract_content": f'"{literal}"'}}}}
        for path, check_id, line, literal in results
    ]})


def test_pr1_path_is_directed(tmp_path):
    """PR-1: an edge A→B must not create a path B→A."""
    index = CodeIndex(tmp_path / "code.sqlite").open()
    index.ingest_astgrep(_astgrep_ndjson(
        ("a.rs", "kotlin.function", "caller", 1),
        ("a.rs", "kotlin.function", "callee", 5),
    ), scan_run_id="s1", scan_root=tmp_path)
    index.ingest_semgrep(_semgrep_json(
        ("a.rs", "http.client.call", 2, "http://api"),
    ), scan_run_id="s1", scan_root=tmp_path)

    caller = index.resolve("a.rs::caller@1")
    edge = index.outgoing(caller["id"])[0]
    target_id = edge["target_id"]

    assert index.path(caller["id"], target_id) is not None
    assert index.path(target_id, caller["id"]) is None


def test_pr2_new_generation_replaces_previous(tmp_path):
    """PR-2: index(generation N+1) contains exactly the facts of N+1 —
    facts of a retired generation never survive."""
    index = CodeIndex(tmp_path / "code.sqlite").open()
    index.ingest_astgrep(_astgrep_ndjson(
        ("a.rs", "kotlin.function", "fun kept()", 1),
        ("b.rs", "kotlin.function", "fun removed()", 1),
    ), scan_run_id="gen-1", scan_root=tmp_path)
    index.ingest_semgrep(_semgrep_json(
        ("a.rs", "http.client.call", 2, "http://old"),
    ), scan_run_id="gen-1", scan_root=tmp_path)
    assert index.stats()["files"] == 2

    index.ingest_astgrep(_astgrep_ndjson(
        ("a.rs", "kotlin.function", "fun kept()", 1),
    ), scan_run_id="gen-2", scan_root=tmp_path)
    index.ingest_semgrep(_semgrep_json(
        ("a.rs", "http.client.call", 2, "http://new"),
    ), scan_run_id="gen-2", scan_root=tmp_path)

    stats = index.stats()
    assert stats["files"] == 1
    assert stats["symbols"] == 2          # kept() + the gen-2 pseudo-target
    assert stats["edges"] == 1
    assert index.search_symbol("removed") == []
    runs = {r["scan_run_id"] for r in
            index._db.execute("SELECT scan_run_id FROM files").fetchall()}
    assert runs == {"gen-2"}

    # Same-run re-ingest stays idempotent.
    index.ingest_astgrep(_astgrep_ndjson(
        ("a.rs", "kotlin.function", "fun kept()", 1),
    ), scan_run_id="gen-2", scan_root=tmp_path)
    assert index.stats()["files"] == 1


def test_pr3_promote_is_diff_fixpoint(kotlin_world_index):
    """PR-3: promote(main, proposal) ⇒ structural_diff(main, proposal)
    is empty — removals included."""
    world, index = kotlin_world_index
    discover(world, index, scan_run_id=KOTLIN_RUN)

    fork = world.fork("pr3-fixpoint")
    victim = fork.architecture_relations()[0]
    fork.graph.remove_relation(victim["id"])
    fork.record_proposal("pr3-fixpoint")
    fork.approve_proposal("pr3-fixpoint", actor="property-test")

    summary = promote(world, fork)
    assert summary["relations_removed"] == 1

    diff = structural_diff(world, fork)
    assert diff.is_empty(), (
        f"promotion is not a diff fixpoint: {diff}")


def test_pr4_manual_edit_blocks_regeneration(kotlin_world_index):
    """PR-4: a hand-edited artifact must refuse regeneration without
    force (content-based detection, not a sidecar flag)."""
    world, index = kotlin_world_index
    discover(world, index, scan_run_id=KOTLIN_RUN)
    result = project_to_workspace(world, LikeC4Adapter())
    artifact_path = result["path"]

    with open(artifact_path, "a") as artifact:
        artifact.write("\n// hand edit\n")

    with pytest.raises(ProjectionError, match="manually modified"):
        project_to_workspace(world, LikeC4Adapter())

    regenerated = project_to_workspace(world, LikeC4Adapter(), force=True)
    assert regenerated["path"] == artifact_path
    project_to_workspace(world, LikeC4Adapter())  # hash now matches again


def test_pr5_cardinality_gates_contradiction(kotlin_world_index):
    """PR-5: contradiction only on single-valued predicates."""
    world, _ = kotlin_world_index
    for obj in ("GET /a", "POST /b", "DELETE /c"):
        world.record_observation(inferred_observation(
            subject="svc.orders", predicate="exposes", obj=obj))
    world.record_observation(inferred_observation(
        subject="svc.orders", predicate="belongs_to", obj="domain.orders"))
    world.record_observation(inferred_observation(
        subject="svc.orders", predicate="belongs_to", obj="domain.billing"))
    propose_claims(world)
    counts = evaluate_claims(world)
    assert counts["contradicted"] == 2          # the belongs_to pair only
    exposes = [c for c in world.find_objects("claim")
               if c["data"]["statement"].startswith("svc.orders exposes")]
    assert len(exposes) == 3
    assert all(c["data"]["status"] == "proposed" for c in exposes)
