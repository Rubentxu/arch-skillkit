"""F7 — real architecture drift from scan-generation deltas (docs/v2/46)."""

import json

from archskillkit.codeindex import CodeIndex
from archskillkit.promotion import detect_generation_drift
from archskillkit.world import ArchitectureWorld


def _astgrep_ndjson(*records: tuple[str, str, str, int]) -> str:
    lines = []
    for file_path, rule_id, text, line in records:
        lines.append(json.dumps({
            "file": file_path, "ruleId": rule_id, "text": text,
            "range": {"start": {"line": line - 1}},
            "lines": text,
        }))
    return "\n".join(lines)


def _semgrep_json(*results: tuple[str, str, int, str]) -> str:
    return json.dumps({"results": [
        {"check_id": check_id, "path": path,
         "start": {"line": line},
         "extra": {"metavars": {"$X": {"abstract_content": f'"{literal}"'}}}}
        for path, check_id, line, literal in results
    ]})


def _repo(tmp_path):
    import subprocess
    repo = tmp_path / "drift-fixture"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin",
                    "https://github.com/rubentxu/drift-fixture.git"],
                   check=True)
    return repo


def test_generation_rotation_keeps_previous_queryable(tmp_path):
    index = CodeIndex(tmp_path / "code.sqlite").open()
    index.ingest_astgrep(_astgrep_ndjson(
        ("a.rs", "kotlin.function", "caller", 1),
    ), scan_run_id="gen-1", scan_root=tmp_path)
    index.ingest_semgrep(_semgrep_json(
        ("a.rs", "http.client.call", 2, "http://old"),
    ), scan_run_id="gen-1", scan_root=tmp_path)

    index.ingest_astgrep(_astgrep_ndjson(
        ("a.rs", "kotlin.function", "caller", 1),
    ), scan_run_id="gen-2", scan_root=tmp_path)
    index.ingest_semgrep(_semgrep_json(
        ("a.rs", "http.client.call", 2, "http://new"),
    ), scan_run_id="gen-2", scan_root=tmp_path)

    assert index.previous_generation_run() == "gen-1"
    assert (tmp_path / "code.prev.sqlite").exists()
    diff = index.diff_previous_generation()
    assert diff["previous_generation"] == "gen-1"
    assert diff["current_generation"] == "gen-2"
    assert len(diff["added"]) == 1
    assert len(diff["removed"]) == 1
    assert "http://new" in diff["added"][0][2]
    assert "http://old" in diff["removed"][0][2]


def test_no_previous_generation_means_empty_delta(tmp_path):
    index = CodeIndex(tmp_path / "code.sqlite").open()
    index.ingest_astgrep(_astgrep_ndjson(
        ("a.rs", "kotlin.function", "caller", 1),
    ), scan_run_id="gen-1", scan_root=tmp_path)
    diff = index.diff_previous_generation()
    assert diff["previous_generation"] is None
    assert diff["added"] == []


def test_generation_drift_persists_new_dependency_findings(tmp_path,
                                                           monkeypatch):
    for var in ("XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CONFIG_HOME",
                "XDG_CACHE_HOME"):
        monkeypatch.setenv(var, str(tmp_path / var.lower()))
    repo = _repo(tmp_path)

    world = ArchitectureWorld.for_repo(repo).open()
    world.ensure_project()
    index = CodeIndex(world.workspace / "code.sqlite").open()

    # generation 1: no meaningful dependency edges
    index.ingest_astgrep(_astgrep_ndjson(
        ("src/orders.rs", "kotlin.function", "create_order", 1),
    ), scan_run_id="gen-1", scan_root=tmp_path)
    index.ingest_semgrep("{}", scan_run_id="gen-1", scan_root=tmp_path)

    # generation 2: the code gains a datastore dependency
    index.ingest_astgrep(_astgrep_ndjson(
        ("src/orders.rs", "kotlin.function", "create_order", 1),
    ), scan_run_id="gen-2", scan_root=tmp_path)
    index.ingest_semgrep(_semgrep_json(
        ("src/orders.rs", "persistence.repository.save", 3, "orders_db"),
    ), scan_run_id="gen-2", scan_root=tmp_path)

    report = detect_generation_drift(world, index)
    assert report["generation"] == "gen-1"
    assert len(report["findings"]) == 1
    finding = report["findings"][0]
    assert finding["kind"] == "generation_drift"
    assert "uses dependency" in finding["detail"]
    assert "src/orders.rs::create_order@1" in finding["detail"]
    assert report["persisted"] == 1

    # dedup: re-evaluating the same delta persists nothing new
    second = detect_generation_drift(world, index)
    assert second["persisted"] == 0
