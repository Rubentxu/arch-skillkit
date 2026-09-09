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

    def test_codeindex_satisfies_protocol_structurally(self):
        """CodeIndex (the concrete impl) must satisfy the Protocol
        without inheriting from it (structural typing)."""
        from archskillkit.codegraph import CodeGraphQueryPort
        from archskillkit.codeindex import CodeIndex
        assert issubclass(CodeIndex, CodeGraphQueryPort)

    def test_runtime_checkable_accepts_codeindex_instance(self):
        from archskillkit.codegraph import CodeGraphQueryPort, satisfies_port
        from archskillkit.codeindex import CodeIndex

        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tf:
            path = tf.name
        try:
            ci = CodeIndex(path).open()
            try:
                assert satisfies_port(ci)
                assert isinstance(ci, CodeGraphQueryPort)
            finally:
                ci.close()
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
                assert c["count"] == 0, (
                    f"ARC-010 should be 0 after M5; got {c['count']}: {violations}"
                )
