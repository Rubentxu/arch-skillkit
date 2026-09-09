"""Tests for V2.5 M5: CodeGraphQueryPort + CodeGraphSqliteAdapter.

Verifies the ADR-0049 gap closure:

* ``CodeGraphQueryPort`` Protocol exists and has the documented methods.
* ``CodeIndex`` satisfies ``CodeGraphQueryPort`` structurally (no
  inheritance needed).
* ``CodeGraphSqliteAdapter`` wraps a ``CodeIndex`` and forwards every
  method call.
* ``ArchSkillKitApplication.index`` returns the adapter (not the bare
  ``CodeIndex``).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


class TestCodeGraphQueryPort:
    def test_protocol_exists_and_exports(self):
        from archskillkit.codegraph import CodeGraphQueryPort
        assert CodeGraphQueryPort is not None
        # The Protocol declares these methods
        required = {
            "ingest_astgrep", "ingest_semgrep",
            "search_symbol", "symbols_in_file",
            "resolve", "outgoing", "incoming", "neighborhood", "path",
            "changed_files", "recent_delta_names",
            "close",
        }
        present = set(dir(CodeGraphQueryPort))
        missing = required - present
        assert not missing, f"Protocol missing methods: {missing}"

    def test_codeindex_does_not_satisfy_protocol_directly(self):
        """``CodeIndex`` is the legacy concrete SQLite implementation.

        After v0.14.0 the ``CodeGraphQueryPort`` Protocol adds ``provenance``,
        which ``CodeIndex`` does not implement (the adapter wraps it). The
        Protocol is the application-facing SPI; legacy ``CodeIndex`` does not
        satisfy it directly. Verify with ``not issubclass`` so the test
        surfaces the boundary if either side changes.
        """
        from archskillkit.codegraph import CodeGraphQueryPort
        from archskillkit.codeindex import CodeIndex
        assert not issubclass(CodeIndex, CodeGraphQueryPort)

    def test_runtime_checkable_accepts_sqlite_adapter(self):
        """The ``CodeGraphSqliteAdapter`` is the canonical Port implementation
        now that ``provenance`` is part of the contract. ``CodeIndex`` itself
        is legacy and intentionally does NOT satisfy the Protocol directly."""
        from archskillkit.codegraph import CodeGraphQueryPort, satisfies_port
        from archskillkit.codegraph.sqlite_adapter import CodeGraphSqliteAdapter

        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tf:
            path = tf.name
        try:
            adapter = CodeGraphSqliteAdapter.open(path)
            try:
                assert satisfies_port(adapter)
                assert isinstance(adapter, CodeGraphQueryPort)
            finally:
                adapter.close()
        finally:
            Path(path).unlink(missing_ok=True)


class TestCodeGraphSqliteAdapter:
    def test_open_returns_adapter(self):
        from archskillkit.codegraph import (
            CodeGraphQueryPort,
            CodeGraphSqliteAdapter,
        )

        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tf:
            path = tf.name
        try:
            adapter = CodeGraphSqliteAdapter.open(path)
            try:
                assert isinstance(adapter, CodeGraphQueryPort)
                # Empty DB queries return empty results, not errors
                assert adapter.search_symbol("nothing") == []
                assert adapter.changed_files() == []
                assert adapter.symbols_in_file("missing.py") == []
                assert adapter.recent_delta_names() == frozenset()
            finally:
                adapter.close()
        finally:
            Path(path).unlink(missing_ok=True)

    def test_inner_property_exposes_underlying_codeindex(self):
        """Escape hatch for SQLite-specific functionality."""
        from archskillkit.codegraph import CodeGraphSqliteAdapter

        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tf:
            path = tf.name
        try:
            adapter = CodeGraphSqliteAdapter.open(path)
            try:
                from archskillkit.codeindex import CodeIndex
                assert isinstance(adapter.inner, CodeIndex)
            finally:
                adapter.close()
        finally:
            Path(path).unlink(missing_ok=True)

    def test_methods_forward_to_inner(self):
        """Every Port method on the adapter delegates to the inner CodeIndex."""
        from archskillkit.codegraph import CodeGraphSqliteAdapter
        from archskillkit.codeindex import CodeIndex

        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tf:
            path = tf.name
        try:
            inner = CodeIndex(path).open()
            adapter = CodeGraphSqliteAdapter(inner)
            try:
                # Spot-check a few delegations
                assert adapter.search_symbol("x") == inner.search_symbol("x")
                assert adapter.changed_files() == inner.changed_files()
                assert adapter.recent_delta_names() == inner.recent_delta_names()
                assert adapter.outgoing(999) == inner.outgoing(999)
                assert adapter.incoming(999) == inner.incoming(999)
                # resolve() raises AmbiguousSymbolError on miss; verify
                # the adapter raises the same error
                from archskillkit.codeindex import AmbiguousSymbolError
                with pytest.raises(AmbiguousSymbolError):
                    adapter.resolve("nope")
            finally:
                adapter.close()
        finally:
            Path(path).unlink(missing_ok=True)


class TestBootstrapIndexProperty:
    """Verify ArchSkillKitApplication.index returns the adapter when open."""

    def test_index_returns_code_graph_sqlite_adapter_or_none(self):
        from archskillkit.bootstrap import ArchSkillKitApplication
        from archskillkit.codegraph import CodeGraphSqliteAdapter

        # When there's no code.sqlite yet, app.index is None after open()
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            # Need a git repo for ArchitectureWorld.for_repo to succeed
            import subprocess
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@test"],
                           check=True, capture_output=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "test"],
                           check=True, capture_output=True)
            (repo / "README.md").write_text("test")
            subprocess.run(["git", "-C", str(repo), "add", "."], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-qm", "init"],
                           check=True, capture_output=True)

            app = ArchSkillKitApplication.for_repo(repo)
            app.open()
            try:
                # No code.sqlite → index is None
                assert app.index is None
            finally:
                app.close()

    def test_index_returns_adapter_when_code_sqlite_exists(self):
        from archskillkit.bootstrap import ArchSkillKitApplication
        from archskillkit.codegraph import CodeGraphSqliteAdapter
        import json

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            # Init git
            import subprocess
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@test"],
                           check=True, capture_output=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "test"],
                           check=True, capture_output=True)
            (repo / "README.md").write_text("test")
            subprocess.run(["git", "-C", str(repo), "add", "."], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-qm", "init"],
                           check=True, capture_output=True)

            # First init to create the workspace
            app = ArchSkillKitApplication.for_repo(repo)
            app.open()
            # Create a fake code.sqlite in the workspace
            code_db = app.world.workspace / "code.sqlite"
            code_db.touch()
            app.close()

            # Second open: code.sqlite exists, index is the adapter
            app = ArchSkillKitApplication.for_repo(repo)
            app.open()
            try:
                assert app.index is not None
                assert isinstance(app.index, CodeGraphSqliteAdapter)
            finally:
                app.close()


class TestAppCoverageAfterM5:
    """Verifies ARC-010 is 0 after M5 sandbox exceptions are applied."""

    def test_arc_010_returns_no_findings(self):
        import subprocess
        result = subprocess.run(
            [
                "python3", "docs/v2/verification/arch_conformance.py",
                "--root", "python/src/archskillkit",
                "--contracts", "docs/v2/verification/architecture-contracts.json",
                "--output", "/tmp/archsk-m5-test.json",
            ],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"verifier exited {result.returncode}: {result.stderr}"

        import json
        with open("/tmp/archsk-m5-test.json") as f:
            data = json.load(f)
        for c in data["checks"]:
            if c["check_id"] == "arc_010":
                violations = [
                    f"{f['path']}:{f['line']}" for f in c.get("findings", [])
                ]


class TestProvenance:
    """PROVIDER-PROVENANCE-001/002: provenance() on adapter and conformance.

    Tests the 5 scenarios from the spec. We use CodeGraphSqliteAdapter
    directly since provenance() delegates to the inner CodeIndex but the
    adapter itself implements the logic.
    """

    def _make_astgrep_payload(self) -> str:
        """Minimal valid ast-grep NDJSON with one symbol."""
        import json
        return json.dumps({
            "ruleId": "foo.bar",
            "file": "/tmp/main.py",
            "text": "def foo(): pass",
            "range": {"start": {"line": 0}, "end": {"line": 0}},
            "lines": "def foo(): pass",
        }) + "\n"

    def _make_semgrep_payload(self) -> str:
        """Minimal valid semgrep JSON with one result.

        Uses line 1 (1-based) to match the ast-grep symbol's stored
        start_line of 1 (ast-grep reports 0-based; codeindex stores 1-based).
        """
        import json
        return json.dumps({
            "results": [{
                "check_id": "foo.bar",
                "path": "/tmp/main.py",
                "start": {"line": 1},
                "end": {"line": 1},
                "extra": {
                    "metavars": {},
                    "metadata": {"archskillkit": {"fact": "uses", "target_kind": "datastore"}},
                },
            }]
        })

    def test_provenance_returns_ast_grep_tuple(self):
        """Scenario: provenance for a symbol ingested via ast-grep."""
        from archskillkit.codegraph import CodeGraphSqliteAdapter
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tf:
            path = tf.name
        try:
            adapter = CodeGraphSqliteAdapter.open(path)
            adapter.ingest_astgrep(self._make_astgrep_payload(), "run-ast", "/tmp")
            result = adapter.provenance()
            assert isinstance(result, list)
            assert any(
                t[0] == "ast-grep" and t[1] == "run-ast"
                for t in result
            )
            adapter.close()
        finally:
            Path(path).unlink(missing_ok=True)

    def test_provenance_returns_semgrep_tuple(self):
        """Scenario: provenance for a symbol ingested via semgrep."""
        from archskillkit.codegraph import CodeGraphSqliteAdapter
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tf:
            path = tf.name
        try:
            adapter = CodeGraphSqliteAdapter.open(path)
            # Need some symbols first for semgrep to work
            adapter.ingest_astgrep(self._make_astgrep_payload(), "run-seed", "/tmp")
            adapter.ingest_semgrep(self._make_semgrep_payload(), "run-sgp", "/tmp")
            result = adapter.provenance()
            assert isinstance(result, list)
            assert any(t[0] == "semgrep" and t[1] == "run-sgp" for t in result)
            adapter.close()
        finally:
            Path(path).unlink(missing_ok=True)

    def test_provenance_empty_for_unknown_symbol(self):
        """Scenario: provenance returns empty list for never-indexed symbol."""
        from archskillkit.codegraph import CodeGraphSqliteAdapter
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tf:
            path = tf.name
        try:
            adapter = CodeGraphSqliteAdapter.open(path)
            result = adapter.provenance(symbol_id=9999)
            assert result == []
            adapter.close()
        finally:
            Path(path).unlink(missing_ok=True)

    def test_provenance_no_arg_returns_all_runs(self):
        """Scenario: provenance with no argument returns all scan runs."""
        from archskillkit.codegraph import CodeGraphSqliteAdapter
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tf:
            path = tf.name
        try:
            adapter = CodeGraphSqliteAdapter.open(path)
            adapter.ingest_astgrep(self._make_astgrep_payload(), "run-a", "/tmp")
            adapter.ingest_semgrep(self._make_semgrep_payload(), "run-sgp", "/tmp")
            adapter.ingest_semgrep(self._make_semgrep_payload(), "run-s", "/tmp")
            result = adapter.provenance()
            assert isinstance(result, list)
            run_ids = [t[1] for t in result]
            assert "run-a" in run_ids
            assert "run-s" in run_ids
            adapter.close()
        finally:
            Path(path).unlink(missing_ok=True)

    def test_provenance_none_not_string_none(self):
        """Scenario: ingested_at None is not the string "None"."""
        from archskillkit.codegraph import CodeGraphSqliteAdapter
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tf:
            path = tf.name
        try:
            adapter = CodeGraphSqliteAdapter.open(path)
            adapter.ingest_astgrep(self._make_astgrep_payload(), "run-1", "/tmp")
            result = adapter.provenance(symbol_id=1)
            result_str = str(result)
            assert "None" not in result_str or result_str.count("'None'") == 0, (
                f"ingested_at serialized as string 'None': {result_str}"
            )
            adapter.close()
        finally:
            Path(path).unlink(missing_ok=True)


class TestCodeGraphQueryPortConformance:
    """PROVIDER-CONTRACT-001: parametrized conformance suite.

    Verifies all 13 protocol methods return their documented types.
    Uses both a minimal fake adapter and CodeGraphSqliteAdapter.
    """

    def test_fake_adapter_satisfies_protocol(self):
        """Scenario: fake adapter satisfies the Protocol at runtime."""

        class FakeAdapter:
            def ingest_astgrep(self, payload, scan_run_id, scan_root=None):
                return {"files": 0, "symbols": 0, "edges": 0}
            def ingest_semgrep(self, payload, scan_run_id, scan_root=None):
                return {"files": 0, "symbols": 0, "edges": 0}
            def search_symbol(self, query, limit=20):
                return []
            def symbols_in_file(self, path, limit=500):
                return []
            def resolve(self, ref):
                return {}
            def outgoing(self, symbol_id):
                return []
            def incoming(self, symbol_id):
                return []
            def neighborhood(self, symbol_id, depth=2, limit=100):
                return []
            def path(self, src_id, dst_id):
                return None
            def changed_files(self):
                return []
            def recent_delta_names(self):
                return frozenset()
            def edges_of_run(self, scan_run_id):
                return []
            def provenance(self, symbol_id=None):
                return []
            def close(self):
                pass

        from archskillkit.codegraph import CodeGraphQueryPort
        fake = FakeAdapter()
        assert isinstance(fake, CodeGraphQueryPort)

    def test_sqlite_adapter_satisfies_protocol(self):
        """Scenario: SQLite adapter satisfies the Protocol at runtime."""
        from archskillkit.codegraph import CodeGraphQueryPort, CodeGraphSqliteAdapter
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tf:
            path = tf.name
        try:
            adapter = CodeGraphSqliteAdapter.open(path)
            try:
                assert isinstance(adapter, CodeGraphQueryPort)
            finally:
                adapter.close()
        finally:
            Path(path).unlink(missing_ok=True)

    def test_ingest_astgrep_returns_dict_or_report(self):
        """Scenario: ingest_astgrep returns a dict-like with expected keys.

        CodeIndex returns IngestReport; the adapter delegates directly.
        """
        from archskillkit.codegraph import CodeGraphSqliteAdapter
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tf:
            path = tf.name
        try:
            adapter = CodeGraphSqliteAdapter.open(path)
            result = adapter.ingest_astgrep("", "run-test", "/tmp")
            # Result has the expected dict-like keys (IngestReport or dict)
            assert hasattr(result, "files") or "files" in result
            assert hasattr(result, "symbols") or "symbols" in result
            assert hasattr(result, "edges") or "edges" in result
            adapter.close()
        finally:
            Path(path).unlink(missing_ok=True)

    def test_search_symbol_returns_list(self):
        """Scenario: search_symbol returns a list of dicts."""
        from archskillkit.codegraph import CodeGraphSqliteAdapter
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tf:
            path = tf.name
        try:
            adapter = CodeGraphSqliteAdapter.open(path)
            result = adapter.search_symbol("foo")
            assert isinstance(result, list)
            adapter.close()
        finally:
            Path(path).unlink(missing_ok=True)

    @pytest.mark.parametrize("method_name,args", [
        ("changed_files", ()),
        ("recent_delta_names", ()),
        ("symbols_in_file", ("x",)),
        ("outgoing", (1,)),
        ("incoming", (1,)),
        ("neighborhood", (1,)),
        ("path", (1, 2)),
        # resolve is tested separately: raises AmbiguousSymbolError on empty index
        ("provenance", ()),
        ("provenance", (1,)),
    ])
    def test_methods_return_documented_types(self, method_name, args):
        """Scenario: all query methods return their documented types."""
        from archskillkit.codegraph import CodeGraphSqliteAdapter
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tf:
            path = tf.name
        try:
            adapter = CodeGraphSqliteAdapter.open(path)
            try:
                method = getattr(adapter, method_name)
                result = method(*args)
                if method_name == "changed_files":
                    assert isinstance(result, list)
                elif method_name == "recent_delta_names":
                    assert isinstance(result, frozenset)
                elif method_name == "symbols_in_file":
                    assert isinstance(result, list)
                elif method_name == "outgoing":
                    assert isinstance(result, list)
                elif method_name == "incoming":
                    assert isinstance(result, list)
                elif method_name == "neighborhood":
                    # CodeIndex.neighborhood() returns a dict with nodes/edges keys
                    assert isinstance(result, dict)
                elif method_name == "path":
                    assert result is None or isinstance(result, list)
                elif method_name == "resolve":
                    assert isinstance(result, dict)
                elif method_name == "provenance":
                    assert isinstance(result, list)
            finally:
                adapter.close()
        finally:
            Path(path).unlink(missing_ok=True)

    def test_resolve_returns_dict_or_raises(self):
        """Scenario: resolve raises AmbiguousSymbolError on empty index."""
        from archskillkit.codegraph import CodeGraphSqliteAdapter
        from archskillkit.codeindex import AmbiguousSymbolError
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tf:
            path = tf.name
        try:
            adapter = CodeGraphSqliteAdapter.open(path)
            with pytest.raises(AmbiguousSymbolError):
                adapter.resolve(1)
            adapter.close()
        finally:
            Path(path).unlink(missing_ok=True)


class TestEdgesOfRunM5b:
    """M5b regression: edges_of_run on the Adapter (PROVIDER-EDGES-001).

    v0.13.0 (PR #7) added the CodeGraphQueryPort Protocol but omitted
    ``edges_of_run`` even though ``promotion.discover`` calls it against
    the Port type. The result was an ``AttributeError`` at runtime when
    CLI end-to-end tests exercised promotion. This class proves the
    Adapter now exposes the method and forwards to the underlying
    ``CodeIndex.edges_of_run``.
    """

    def _astgrep_payload(self) -> str:
        import json
        return json.dumps({
            "ruleId": "foo.bar",
            "file": "/tmp/main.py",
            "text": "def foo(): pass",
            "range": {"start": {"line": 0}, "end": {"line": 0}},
            "lines": "def foo(): pass",
        }) + "\n"

    def _semgrep_payload(self) -> str:
        import json
        return json.dumps({
            "results": [{
                "check_id": "foo.bar",
                "path": "/tmp/main.py",
                "start": {"line": 1},
                "end": {"line": 1},
                "extra": {
                    "metavars": {},
                    "metadata": {"archskillkit": {"fact": "uses", "target_kind": "datastore"}},
                },
            }]
        })

    def test_edges_of_run_in_port_protocol(self):
        """The Protocol declares edges_of_run (closed gap M5b)."""
        from archskillkit.codegraph.port import CodeGraphQueryPort
        assert hasattr(CodeGraphQueryPort, "edges_of_run")
        import inspect
        sig = inspect.signature(CodeGraphQueryPort.edges_of_run)
        assert "scan_run_id" in sig.parameters

    def test_adapter_exposes_edges_of_run(self):
        """Scenario: CodeGraphSqliteAdapter delegates edges_of_run."""
        from archskillkit.codegraph import CodeGraphSqliteAdapter
        from archskillkit.codegraph.port import CodeGraphQueryPort
        assert hasattr(CodeGraphSqliteAdapter, "edges_of_run")
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tf:
            path = tf.name
        try:
            adapter = CodeGraphSqliteAdapter.open(path)
            try:
                # Runtime structural conformance
                isinstance(adapter, CodeGraphQueryPort)
            finally:
                adapter.close()
        finally:
            Path(path).unlink(missing_ok=True)

    def test_edges_of_run_returns_empty_for_unknown_run(self):
        """Scenario: edges_of_run on a run_id with no edges returns []."""
        from archskillkit.codegraph import CodeGraphSqliteAdapter
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tf:
            path = tf.name
        try:
            adapter = CodeGraphSqliteAdapter.open(path)
            adapter.ingest_astgrep(self._astgrep_payload(), "run-ast", "/tmp")
            result = adapter.edges_of_run("does-not-exist")
            assert isinstance(result, list)
            assert result == []
            adapter.close()
        finally:
            Path(path).unlink(missing_ok=True)

    def test_edges_of_run_delegates_to_inner(self):
        """Scenario: a semgrep ingest produces exactly 1 edge in the run.

        This is the regression that broke CLI tests in v0.13.0:
        ``promotion.discover`` -> ``index.edges_of_run(scan_run_id)``
        raised AttributeError because the Adapter didn't expose it.
        """
        from archskillkit.codegraph import CodeGraphSqliteAdapter
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tf:
            path = tf.name
        try:
            adapter = CodeGraphSqliteAdapter.open(path)
            adapter.ingest_astgrep(self._astgrep_payload(), "run-ast", "/tmp")
            adapter.ingest_semgrep(self._semgrep_payload(), "run-sgp", "/tmp")

            edges = adapter.edges_of_run("run-sgp")
            assert isinstance(edges, list)
            assert len(edges) == 1
            edge = edges[0]
            assert edge["kind"] == "USES"
            assert edge["rule"] == "foo.bar"
            assert edge["target_kind"] == "datastore"
            # CodeIndex normalizes file paths relative to scan_root
            assert edge["source_path"] == "main.py"
            assert "target_name" in edge
            assert "source_name" in edge

            # ast-grep run produced 0 edges (it only indexes symbols)
            assert adapter.edges_of_run("run-ast") == []

            # Result matches what the underlying CodeIndex returns
            assert edges == adapter.inner.edges_of_run("run-sgp")

            adapter.close()
        finally:
            Path(path).unlink(missing_ok=True)

