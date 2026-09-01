"""V2 Phase B — Code Index (code.sqlite): schema, ingestion, queries.

M2-B1 schema, M2-B2 ast-grep ingestion, M2-B3 Semgrep ingestion,
M2-B4 query API (docs/v2/05-code-index.md). The ingestion tests run
against REAL scanner payloads captured from the pinned V1 toolchain
(python/tests/fixtures/*.json, paths normalized to a virtual scan root),
plus synthetic payloads for topology control. Graph A invariants hold:
regenerable, deterministic, completely separate from the Architecture
World.
"""

import json
import sqlite3
import subprocess
import time
from pathlib import Path

import pytest

from archskillkit.codeindex import (
    AmbiguousSymbolError,
    CodeIndex,
    IngestError,
    SchemaVersionMismatch,
)
from archskillkit.world import ArchitectureWorld

FIXTURES = Path(__file__).parent / "fixtures"
FX_ROOT = FIXTURES  # scan root used to relativize absolute paths


def load_fixtures(name: str) -> str:
    return (FIXTURES / name).read_text()


@pytest.fixture()
def index(tmp_path):
    idx = CodeIndex(tmp_path / "code.sqlite").open()
    yield idx
    idx.close()


def ndjson(*records: dict) -> str:
    return "\n".join(json.dumps(r) for r in records) + "\n"


def outline_record(rule: str, name: str, file: str, line: int, language: str) -> dict:
    return {
        "ruleId": rule,
        "text": name,
        "file": str(FX_ROOT / file),
        "range": {"start": {"line": line, "column": 0}, "end": {"line": line, "column": 10}},
        "lines": f"{name}()",
        "language": language,
        "metaVariables": {"single": {}, "multi": {}},
    }


def semgrep_result(check_id: str, path: str, line: int) -> dict:
    return {
        "check_id": check_id,
        "path": path,
        "start": {"line": line, "col": 1},
        "end": {"line": line, "col": 30},
        "extra": {"message": "m", "metavars": {}, "lines": "requires login"},
    }


def add_edge(index, src_name: str, dst_name: str, kind: str = "CALLS",
             rule: str = "test", run: str = "r1") -> None:
    index._conn.execute(
        "INSERT INTO edges (source_id, target_id, kind, origin, rule,"
        " confidence, scan_run_id) SELECT s.id, t.id, ?, 'DETECTED', ?, 'high', ?"
        " FROM symbols s, symbols t WHERE s.name=? AND t.name=?",
        (kind, rule, run, src_name, dst_name))
    index._conn.commit()


class TestSchema:
    def test_create_is_idempotent(self, tmp_path):
        db = tmp_path / "code.sqlite"
        CodeIndex(db).open().close()
        CodeIndex(db).open().close()  # reopen does not raise nor wipe

    def test_schema_version_guard(self, tmp_path):
        db = tmp_path / "code.sqlite"
        CodeIndex(db).open().close()
        conn = sqlite3.connect(db)
        conn.execute("UPDATE meta SET value='999' WHERE key='schema_version'")
        conn.commit()
        conn.close()
        with pytest.raises(SchemaVersionMismatch):
            CodeIndex(db).open()

    def test_tables_exist(self, index):
        names = {
            r[0] for r in index._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert {"meta", "files", "symbols", "edges"} <= names

    def test_file_deletion_cascades_to_symbols(self, index):
        index.ingest_astgrep(
            ndjson(outline_record("outline.rust.struct", "Order", "a.rs", 0, "Rust")),
            scan_run_id="r1", scan_root=FX_ROOT)
        assert index.stats()["symbols"] == 1
        index._conn.execute("DELETE FROM files")
        index._conn.commit()
        assert index.stats()["symbols"] == 0


class TestAstgrepIngest:
    def test_real_rust_fixture(self, index):
        report = index.ingest_astgrep(
            load_fixtures("astgrep-rust.json"), scan_run_id="r1", scan_root=FX_ROOT)
        assert report.symbols == 10
        assert report.files == 2  # api.rs, domain.rs
        assert report.kinds["function"] == 6
        assert report.kinds["trait"] == 1
        assert report.kinds["struct"] == 2
        assert report.kinds["enum"] == 1

    def test_real_kotlin_fixture_counts(self, index):
        report = index.ingest_astgrep(
            load_fixtures("astgrep-kotlin.json"), scan_run_id="r1", scan_root=FX_ROOT)
        assert report.symbols == 18
        assert report.kinds["type"] == 10
        assert report.kinds["function"] == 8

    def test_real_typescript_fixture_counts(self, index):
        report = index.ingest_astgrep(
            load_fixtures("astgrep-ts.json"), scan_run_id="r1", scan_root=FX_ROOT)
        assert report.symbols == 5
        assert report.kinds["interface"] == 2

    def test_paths_relative_and_lines_one_based(self, index):
        index.ingest_astgrep(
            load_fixtures("astgrep-rust.json"), scan_run_id="r1", scan_root=FX_ROOT)
        row = index.search_symbol("get_order")[0]
        assert row["path"] == "rust-hexagonal/src/api.rs"
        # ast-grep reports 0-based lines; the index stores 1-based
        assert row["start_line"] == 5

    def test_same_name_twice_is_two_rows(self, index):
        # Orders.kt has findById at ast-grep lines 7 and 15 (0-based)
        index.ingest_astgrep(
            load_fixtures("astgrep-kotlin.json"), scan_run_id="r1", scan_root=FX_ROOT)
        rows = index.search_symbol("findById")
        assert len(rows) == 2
        assert {r["start_line"] for r in rows} == {8, 16}

    def test_absolute_paths_are_relativized(self, index):
        # outline_record uses an absolute path under FX_ROOT
        index.ingest_astgrep(
            ndjson(outline_record("outline.rust.struct", "Order", "a.rs", 0, "Rust")),
            scan_run_id="r1", scan_root=FX_ROOT)
        assert index.search_symbol("Order")[0]["path"] == "a.rs"

    def test_empty_payload_ok(self, index):
        report = index.ingest_astgrep("", scan_run_id="r1", scan_root=FX_ROOT)
        assert report.symbols == 0 and report.files == 0

    def test_malformed_jsonl_is_atomic(self, index):
        index.ingest_astgrep(
            ndjson(outline_record("outline.rust.struct", "Order", "a.rs", 0, "Rust")),
            scan_run_id="r1", scan_root=FX_ROOT)
        with pytest.raises(IngestError):
            index.ingest_astgrep('{"text": broken\n', scan_run_id="r2", scan_root=FX_ROOT)
        assert index.stats()["symbols"] == 1  # nothing from the bad run leaked


class TestSemgrepIngest:
    def test_real_kotlin_fixture_edges(self, index):
        index.ingest_astgrep(
            load_fixtures("astgrep-kotlin.json"), scan_run_id="r1", scan_root=FX_ROOT)
        report = index.ingest_semgrep(
            load_fixtures("semgrep-kotlin.json"), scan_run_id="r1", scan_root=FX_ROOT)
        assert report.edges == 5
        assert report.edge_kinds["EXPOSES"] == 3
        assert report.edge_kinds["CONSUMES"] == 1
        assert report.edge_kinds["USES"] == 1
        assert report.warnings == []

    def test_endpoint_sources_resolve_to_handler_symbols(self, index):
        index.ingest_astgrep(
            load_fixtures("astgrep-kotlin.json"), scan_run_id="r1", scan_root=FX_ROOT)
        index.ingest_semgrep(
            load_fixtures("semgrep-kotlin.json"), scan_run_id="r1", scan_root=FX_ROOT)
        src = index.resolve("kotlin-spring/src/main/kotlin/demo/infra/Http.kt::getPayment")
        out = index.outgoing(src["id"])
        assert any(e["kind"] == "EXPOSES" and e["target_kind"] == "endpoint" for e in out)

    def test_listener_consumes_topic(self, index):
        index.ingest_astgrep(
            load_fixtures("astgrep-kotlin.json"), scan_run_id="r1", scan_root=FX_ROOT)
        index.ingest_semgrep(
            load_fixtures("semgrep-kotlin.json"), scan_run_id="r1", scan_root=FX_ROOT)
        src = index.resolve("kotlin-spring/src/main/kotlin/demo/infra/Http.kt::onPayment")
        kinds = {e["kind"] for e in index.outgoing(src["id"])}
        assert "CONSUMES" in kinds

    def test_repository_maps_to_datastore(self, index):
        index.ingest_astgrep(
            load_fixtures("astgrep-kotlin.json"), scan_run_id="r1", scan_root=FX_ROOT)
        index.ingest_semgrep(
            load_fixtures("semgrep-kotlin.json"), scan_run_id="r1", scan_root=FX_ROOT)
        src = index.resolve("kotlin-spring/src/main/kotlin/demo/infra/Http.kt::PaymentRepository")
        targets = {(e["kind"], e["target_kind"]) for e in index.outgoing(src["id"])}
        assert ("USES", "datastore") in targets

    def test_unknown_check_id_warns_and_skips(self, index):
        payload = json.dumps({"results": [semgrep_result("custom.weird", "x.rs", 3)]})
        report = index.ingest_semgrep(payload, scan_run_id="r1", scan_root=FX_ROOT)
        assert report.edges == 0
        assert len(report.warnings) == 1

    def test_match_without_container_symbol_skipped_with_warning(self, index):
        # app.ts endpoints: no ast-grep symbols exist in that file
        index.ingest_astgrep(
            load_fixtures("astgrep-ts.json"), scan_run_id="r1", scan_root=FX_ROOT)
        report = index.ingest_semgrep(
            load_fixtures("semgrep-ts.json"), scan_run_id="r1", scan_root=FX_ROOT)
        assert report.edges == 0
        assert len(report.warnings) == 3

    def test_positional_target_names_when_no_metavars(self, index):
        index.ingest_astgrep(
            load_fixtures("astgrep-kotlin.json"), scan_run_id="r1", scan_root=FX_ROOT)
        index.ingest_semgrep(
            load_fixtures("semgrep-kotlin.json"), scan_run_id="r1", scan_root=FX_ROOT)
        src = index.resolve("kotlin-spring/src/main/kotlin/demo/infra/Http.kt::getPayment")
        names = [e["target_name"] for e in index.outgoing(src["id"])]
        assert names == ["endpoint@11"]  # extra.lines is gated in OSS semgrep

    def test_metavar_literal_names_the_target(self, index):
        payload = json.dumps({"results": [{
            **semgrep_result("express.endpoint", "ts-node/app.ts", 6),
            "extra": {"message": "m", "lines": "", "metavars": {
                "$ROUTE": {"abstract_content": '"/orders"', "propagated": False},
            }},
        }]})
        index.ingest_astgrep(
            ndjson(outline_record("outline.typescript.function", "mount",
                                  "ts-node/app.ts", 5, "TypeScript")),
            scan_run_id="r1", scan_root=FX_ROOT)
        index.ingest_semgrep(payload, scan_run_id="r1", scan_root=FX_ROOT)
        src = index.resolve("ts-node/app.ts::mount")
        targets = [e["target_name"] for e in index.outgoing(src["id"])]
        assert targets == ["/orders"]


class TestScanLifecycle:
    def test_same_run_reingest_is_idempotent(self, index):
        ag = load_fixtures("astgrep-kotlin.json")
        sg = load_fixtures("semgrep-kotlin.json")
        index.ingest_astgrep(ag, scan_run_id="r1", scan_root=FX_ROOT)
        index.ingest_semgrep(sg, scan_run_id="r1", scan_root=FX_ROOT)
        baseline = index.stats()
        index.ingest_astgrep(ag, scan_run_id="r1", scan_root=FX_ROOT)
        index.ingest_semgrep(sg, scan_run_id="r1", scan_root=FX_ROOT)
        assert index.stats() == baseline
        assert baseline["edges"] == 5

    def test_regenerate_reproduces_identical_content(self, index):
        ag, sg = load_fixtures("astgrep-kotlin.json"), load_fixtures("semgrep-kotlin.json")
        index.ingest_astgrep(ag, scan_run_id="r1", scan_root=FX_ROOT)
        index.ingest_semgrep(sg, scan_run_id="r1", scan_root=FX_ROOT)
        before = index.stats()
        index.regenerate()
        assert index.stats()["symbols"] == 0
        index.ingest_astgrep(ag, scan_run_id="r1", scan_root=FX_ROOT)
        index.ingest_semgrep(sg, scan_run_id="r1", scan_root=FX_ROOT)
        assert index.stats() == before

    def test_world_survives_index_deletion(self, tmp_path):
        # UAT2-003: code.sqlite is disposable; activegraph.sqlite is not
        repo = tmp_path / "fixture"
        repo.mkdir()
        subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
        subprocess.run(["git", "-C", str(repo), "remote", "add", "origin",
                        "https://github.com/rubentxu/fixture.git"], check=True)
        world = ArchitectureWorld.for_repo(repo).open()
        world.ensure_project()
        world.close()
        code_db = world.workspace / "code.sqlite"
        CodeIndex(code_db).open().close()
        code_db.unlink()
        assert world.db_path.exists()

    def test_two_projects_do_not_share_rows(self, tmp_path):
        a = CodeIndex(tmp_path / "a" / "code.sqlite").open()
        b = CodeIndex(tmp_path / "b" / "code.sqlite").open()
        a.ingest_astgrep(
            ndjson(outline_record("outline.rust.struct", "OnlyA", "a.rs", 0, "Rust")),
            scan_run_id="r", scan_root=FX_ROOT)
        assert a.stats()["symbols"] == 1
        assert b.stats()["symbols"] == 0
        a.close()
        b.close()


class TestQueries:
    """Synthetic call graph:

    load_user -> validate -> save_user -> archive
    load_order -> validate                  (archive reached via USES)
    ghost_note: isolated.
    """

    @pytest.fixture()
    def net(self, index):
        names = ["load_user", "validate", "save_user", "load_order",
                 "archive", "ghost_note"]
        records = [
            outline_record("outline.rust.function", n, "p.rs", i, "Rust")
            for i, n in enumerate(names)
        ]
        index.ingest_astgrep(ndjson(*records), scan_run_id="r1", scan_root=FX_ROOT)
        add_edge(index, "load_user", "validate", "CALLS")
        add_edge(index, "load_order", "validate", "CALLS")
        add_edge(index, "validate", "save_user", "CALLS")
        add_edge(index, "save_user", "archive", "USES")
        return index

    def test_search_token_and_prefix(self, net):
        # implicit prefix: "load" matches load_user and load_order
        assert {r["name"] for r in net.search_symbol("load")} == {
            "load_user", "load_order"}

    def test_search_exact(self, net):
        assert [r["name"] for r in net.search_symbol("validate")] == ["validate"]

    def test_search_no_match_empty(self, net):
        assert net.search_symbol("nonexistent") == []

    def test_search_respects_limit(self, net):
        assert len(net.search_symbol("load", limit=1)) == 1

    def test_resolve_by_qualified_name(self, net):
        assert net.resolve("p.rs::validate@2")["name"] == "validate"

    def test_resolve_by_name_when_unique(self, net):
        assert net.resolve("archive")["name"] == "archive"

    def test_resolve_ambiguous_raises_with_candidates(self, index):
        # a second 'validate' in another file (same generation) makes the
        # bare name ambiguous. V2.3-F1: runs replace, they do not
        # accumulate — cross-run accumulation was the staleness bug.
        index.ingest_astgrep(ndjson(
            outline_record("outline.rust.function", "validate",
                           "p.rs", 1, "Rust"),
            outline_record("outline.kotlin.function", "validate",
                           "q.kt", 0, "Kotlin"),
        ), scan_run_id="r1", scan_root=FX_ROOT)
        with pytest.raises(AmbiguousSymbolError) as exc:
            index.resolve("validate")
        assert len(exc.value.candidates) == 2

    def test_resolve_unknown_raises(self, net):
        with pytest.raises(AmbiguousSymbolError):
            net.resolve("ghost")

    def test_outgoing_and_incoming(self, net):
        validate = net.resolve("p.rs::validate@2")
        out = {e["target_name"] for e in net.outgoing(validate["id"])}
        assert out == {"save_user"}
        inc = {e["source_name"] for e in net.incoming(validate["id"])}
        assert inc == {"load_user", "load_order"}

    def test_neighborhood_bounded_depth(self, net):
        load_user = net.resolve("p.rs::load_user@1")
        depth1 = net.neighborhood(load_user["id"], depth=1)
        assert {n["name"] for n in depth1["nodes"]} == {"load_user", "validate"}
        depth2 = net.neighborhood(load_user["id"], depth=2)
        assert {n["name"] for n in depth2["nodes"]} == {
            "load_user", "validate", "save_user", "load_order"}
        assert "ghost_note" not in {n["name"] for n in depth2["nodes"]}

    def test_neighborhood_max_nodes_cap(self, net):
        load_user = net.resolve("p.rs::load_user@1")
        small = net.neighborhood(load_user["id"], depth=3, max_nodes=2)
        assert len(small["nodes"]) <= 2

    def test_path_found_and_absent(self, net):
        a = net.resolve("p.rs::load_user@1")
        d = net.resolve("p.rs::archive@5")
        z = net.resolve("p.rs::ghost_note@6")
        path = net.path(a["id"], d["id"])
        assert path is not None and len(path) == 4  # load_user, validate, save_user, archive
        assert net.path(a["id"], z["id"]) is None

    def test_impact_transitive_reverse(self, net):
        archive = net.resolve("p.rs::archive@5")
        impacted = {r["name"] for r in net.impact(archive["id"])}
        assert impacted == {"save_user", "validate", "load_user", "load_order"}


class TestScaleSanity:
    def test_1k_symbols_ring_ingest_and_query(self, index):
        records = [
            outline_record("outline.rust.function", f"fn_{i}", "big.rs", i, "Rust")
            for i in range(1000)
        ]
        t0 = time.monotonic()
        index.ingest_astgrep(ndjson(*records), scan_run_id="r1", scan_root=FX_ROOT)
        for i in range(1000):
            add_edge(index, f"fn_{i}", f"fn_{(i + 1) % 1000}")
        ingest_secs = time.monotonic() - t0

        t0 = time.monotonic()
        start = index.resolve("fn_0")["id"]
        hood = index.neighborhood(start, depth=50, max_nodes=100)
        impacted = index.impact(index.resolve("fn_999")["id"])
        query_secs = time.monotonic() - t0

        assert index.stats()["symbols"] == 1000
        assert index.stats()["edges"] == 1000
        assert len(hood["nodes"]) == 100
        assert len(impacted) == 999  # ring: everything reaches fn_999
        assert ingest_secs < 30, f"ingest too slow: {ingest_secs:.1f}s"
        assert query_secs < 30, f"queries too slow: {query_secs:.1f}s"


class TestRepoClean:
    def test_ingest_leaves_repo_untouched(self, tmp_path):
        repo = tmp_path / "fixture"
        (repo / "src").mkdir(parents=True)
        (repo / "src" / "a.rs").write_text("struct Order;\n")
        subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
        subprocess.run(["git", "-C", str(repo), "remote", "add", "origin",
                        "https://github.com/rubentxu/fixture.git"], check=True)
        before = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"],
                                capture_output=True, text=True,
                                check=False).stdout

        idx = CodeIndex.for_repo(repo).open()
        payload = ndjson(outline_record(
            "outline.rust.struct", "Order", "fixture/src/a.rs", 0, "Rust"))
        idx.ingest_astgrep(payload, scan_run_id="r1", scan_root=tmp_path)
        idx.close()

        after = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"],
                               capture_output=True, text=True,
                               check=False).stdout
        assert after == before
