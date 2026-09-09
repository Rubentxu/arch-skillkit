"""``CodeGraphQueryPort`` Protocol (V2.5 M5, ADR-0049).

Application code consumes this Protocol rather than the concrete
``CodeIndex`` class. Providers (SQLite now, ast-grep/Semgrep indexes in
the future, external LSP-backed indexes, ...) implement the Protocol
and are injected via ``ArchSkillKitApplication.index``.

This is the analogue of ``ArchitectureWorldPort`` (``ports.py``) for the
code intelligence side: a structural Protocol, not an inheritance
hierarchy, so existing implementations satisfy it without modification.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class CodeGraphQueryPort(Protocol):
    """Application-facing query surface for the code intelligence layer.

    Every method here is read-only (queries) or ingest-only (the
    ``ingest_*`` family). The Protocol deliberately omits the SQLite
    internals (transactions, schema, raw cursor access) so providers
    are free to choose their own storage.
    """

    # -- ingest (write side) ---------------------------------------------

    def ingest_astgrep(
        self, payload: str, scan_run_id: str, scan_root: str | None = None
    ) -> dict[str, Any]: ...

    def ingest_semgrep(
        self, payload: str, scan_run_id: str, scan_root: str | None = None
    ) -> dict[str, Any]: ...

    # -- queries (read side) ---------------------------------------------

    def search_symbol(self, query: str, limit: int = 20) -> list[dict[str, Any]]: ...

    def symbols_in_file(self, path: str, limit: int = 500) -> list[dict[str, Any]]: ...

    def resolve(self, ref: str | int) -> dict[str, Any]: ...

    def outgoing(self, symbol_id: int) -> list[dict[str, Any]]: ...

    def incoming(self, symbol_id: int) -> list[dict[str, Any]]: ...

    def neighborhood(
        self, symbol_id: int, depth: int = 2, limit: int = 100
    ) -> list[dict[str, Any]]: ...

    def path(self, src_id: int, dst_id: int) -> list[int] | None: ...

    # -- change tracking ---------------------------------------------------

    def changed_files(self) -> list[str]: ...

    def recent_delta_names(self) -> frozenset[str]: ...

    def edges_of_run(self, scan_run_id: str) -> list[dict[str, Any]]:
        """All edges of a scan run with symbol/file context — the input
        the promotion services (M2-C1) turn into observations.

        Added in M5b (v0.13.1) to close the gap where ``promotion.discover``
        called ``index.edges_of_run(...)`` against the Port type but the
        Adapter never delegated it.
        """

    def provenance(self, symbol_id: int | None = None) -> list[tuple[str, str, str | None]]:
        """Return distinct (scanner, scan_run_id, ingested_at) tuples.

        scanner is "ast-grep" for ast-grep scans or "semgrep" for semgrep
        scans. ingested_at is the scan timestamp or None when unavailable.
        When symbol_id is None, all known scan runs are returned.
        """

    # -- lifecycle --------------------------------------------------------

    def close(self) -> None: ...
