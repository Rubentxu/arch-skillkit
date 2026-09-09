"""SQLite-backed adapter for ``CodeGraphQueryPort`` (V2.5 M5, ADR-0049).

Wraps the existing ``archskillkit.codeindex.CodeIndex`` so that:

* The concrete class still owns the SQLite schema, ingest logic, and
  query implementation (no rewrite — 820 LOC stays where it is).
* The application layer can depend on ``CodeGraphQueryPort`` instead of
  ``CodeIndex`` directly.
* Future providers (ast-grep native index, Semgrep SARIF, LSP) can
  satisfy the same Protocol without changing the application.

``CodeIndex`` is structurally compatible with ``CodeGraphQueryPort``:
all methods named in the Protocol already exist on ``CodeIndex`` with
matching signatures. The adapter exists primarily as the named
boundary — it adds nothing at runtime beyond a thin pass-through.
"""

from __future__ import annotations

from typing import Any

from archskillkit.codegraph.port import CodeGraphQueryPort


class CodeGraphSqliteAdapter:
    """Adapts ``CodeIndex`` to the ``CodeGraphQueryPort`` Protocol.

    Holds a reference to the underlying ``CodeIndex`` instance and
    delegates every call. The class is declared ``runtime_checkable``
    via ``CodeGraphQueryPort`` (it satisfies the Protocol structurally).

    Use the factory ``CodeGraphSqliteAdapter.open(db_path)`` in place of
    ``CodeIndex(db_path).open()`` for new code. The legacy constructor
    path remains valid for backward compatibility.
    """

    def __init__(self, inner: Any) -> None:
        # ``inner`` is a CodeIndex (already opened). We accept ``Any`` to
        # break the import cycle: ``codeindex.py`` does not import from
        # this package, so we cannot type-annotate the parameter.
        self._inner = inner
        # Tracks which scanner produced each scan_run_id.
        # Keyed by scan_run_id; values are "ast-grep" or "semgrep".
        self._scanner_by_run: dict[str, str] = {}

    @classmethod
    def open(cls, db_path: str | Any) -> "CodeGraphSqliteAdapter":
        """Open a CodeIndex at ``db_path`` and wrap it in this adapter.

        ``db_path`` can be a path or a ``Path`` object — same as
        ``CodeIndex.__init__``.
        """
        from archskillkit.codeindex import CodeIndex

        return cls(CodeIndex(db_path).open())

    # -- ingest (write side) ---------------------------------------------

    def ingest_astgrep(
        self, payload: str, scan_run_id: str, scan_root: str | None = None
    ) -> dict[str, Any]:
        self._scanner_by_run[scan_run_id] = "ast-grep"
        return self._inner.ingest_astgrep(
            payload, scan_run_id, scan_root=scan_root
        )

    def ingest_semgrep(
        self, payload: str, scan_run_id: str, scan_root: str | None = None
    ) -> dict[str, Any]:
        self._scanner_by_run[scan_run_id] = "semgrep"
        return self._inner.ingest_semgrep(
            payload, scan_run_id, scan_root=scan_root
        )

    # -- queries (read side) ---------------------------------------------

    def search_symbol(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        return self._inner.search_symbol(query, limit=limit)

    def symbols_in_file(self, path: str, limit: int = 500) -> list[dict[str, Any]]:
        return self._inner.symbols_in_file(path, limit=limit)

    def resolve(self, ref: str | int) -> dict[str, Any]:
        return self._inner.resolve(ref)

    def outgoing(self, symbol_id: int) -> list[dict[str, Any]]:
        return self._inner.outgoing(symbol_id)

    def incoming(self, symbol_id: int) -> list[dict[str, Any]]:
        return self._inner.incoming(symbol_id)

    def neighborhood(
        self, symbol_id: int, depth: int = 2, limit: int = 100
    ) -> list[dict[str, Any]]:
        # Note: limit parameter is accepted for Protocol conformance but
        # CodeIndex.neighborhood() does not support it; pass only supported args.
        return self._inner.neighborhood(symbol_id, depth=depth)

    def path(self, src_id: int, dst_id: int) -> list[int] | None:
        return self._inner.path(src_id, dst_id)

    # -- change tracking ---------------------------------------------------

    def changed_files(self) -> list[str]:
        return self._inner.changed_files()

    def recent_delta_names(self) -> frozenset[str]:
        return self._inner.recent_delta_names()

    def edges_of_run(self, scan_run_id: str) -> list[dict[str, Any]]:
        return self._inner.edges_of_run(scan_run_id)

    def provenance(self, symbol_id: int | None = None) -> list[tuple[str, str, str | None]]:
        """Return distinct (scanner, scan_run_id, ingested_at) tuples.

        scanner is "ast-grep" for ast-grep runs or "semgrep" for semgrep
        runs. ingested_at is always None (no timestamp stored in the
        current schema). When symbol_id is None, all known scan runs are
        returned. When symbol_id is given, only runs that contributed
        data for that symbol are returned.
        """
        db = self._inner._db
        seen: set[str] = set()
        result: list[tuple[str, str, str | None]] = []

        if symbol_id is not None:
            # Collect run_ids: semgrep edges + the symbol's file's scan_run_id
            run_ids: set[str] = set()
            edge_runs = db.execute(
                """SELECT DISTINCT e.scan_run_id FROM edges e
                   WHERE e.source_id = ? OR e.target_id = ?""",
                (symbol_id, symbol_id),
            ).fetchall()
            for (run_id,) in edge_runs:
                run_ids.add(run_id)
            # Ast-grep provenance: the file's scan_run_id
            file_run = db.execute(
                """SELECT f.scan_run_id FROM symbols s
                   JOIN files f ON f.id = s.file_id WHERE s.id = ?""",
                (symbol_id,),
            ).fetchone()
            if file_run is not None and file_run[0]:
                run_ids.add(file_run[0])
            for run_id in run_ids:
                scanner = self._scanner_by_run.get(run_id)
                if scanner is not None and run_id not in seen:
                    seen.add(run_id)
                    result.append((scanner, run_id, None))
        else:
            # All runs: union of edges scan_run_ids and files scan_run_ids
            all_runs: set[str] = set()
            for (run_id,) in db.execute(
                "SELECT DISTINCT scan_run_id FROM edges"
            ).fetchall():
                all_runs.add(run_id)
            for (run_id,) in db.execute(
                "SELECT DISTINCT scan_run_id FROM files WHERE scan_run_id != ''"
            ).fetchall():
                all_runs.add(run_id)
            for run_id in sorted(all_runs):
                scanner = self._scanner_by_run.get(run_id)
                if scanner is not None:
                    result.append((scanner, run_id, None))

        return result

    # -- lifecycle --------------------------------------------------------

    def close(self) -> None:
        self._inner.close()

    # -- introspection ----------------------------------------------------

    @property
    def inner(self) -> Any:
        """Access the underlying CodeIndex instance.

        Escape hatch for callers that need SQLite-specific functionality
        not yet covered by the Protocol. New code should not need this.
        """
        return self._inner


def satisfies_port(adapter: Any) -> bool:
    """Check whether ``adapter`` is a valid ``CodeGraphQueryPort``.

    Uses ``isinstance`` with ``@runtime_checkable`` so legacy ``CodeIndex``
    instances satisfy it too (they have all the methods).
    """
    return isinstance(adapter, CodeGraphQueryPort)
