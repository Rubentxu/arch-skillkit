"""Code Index — Graph A (docs/v2/03, docs/v2/05-code-index.md).

A deterministic, regenerable SQLite database of files, symbols and
evidence edges, ingested from V1 scanner payloads (ast-grep outline
NDJSON, Semgrep JSON). Deliberately separate from the Architecture
World: code.sqlite can be deleted and rebuilt at any time without
touching activegraph.sqlite (UAT2-003).

Line convention: ast-grep reports 0-based lines; everything stored here
is 1-based. Paths are stored relative to the scan root so a project id
survives checkouts in different machines.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Self

from archskillkit import sensors
from archskillkit.ids import ProjectContext
from archskillkit.sensors import ContractError

SCHEMA_VERSION = 2

_SYMBOL_KINDS_WITHOUT_HASH = frozenset()

_EXTENSION_LANGUAGES = {
    ".rs": "rust", ".kt": "kotlin", ".kts": "kotlin", ".java": "java",
    ".ts": "typescript", ".tsx": "typescript", ".js": "javascript",
    ".py": "python", ".go": "go",
}

# check_id → (edge kind, pseudo-target kind) mapping is GONE: rules
# declare their contract via metadata.archskillkit (sensors.py). The
# legacy bridge lives there too, for payloads captured before packs
# migrated.


class IngestError(Exception):
    """Scanner payload could not be parsed; nothing was ingested."""


class SchemaVersionMismatch(Exception):
    """code.sqlite was written by a different index schema version."""


class AmbiguousSymbolError(Exception):
    def __init__(self, message: str, candidates: list[dict] | None = None):
        super().__init__(message)
        self.candidates = candidates or []


@dataclass
class IngestReport:
    files: int = 0
    symbols: int = 0
    edges: int = 0
    kinds: dict[str, int] = field(default_factory=dict)
    edge_kinds: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "files": self.files, "symbols": self.symbols, "edges": self.edges,
            "kinds": self.kinds, "edge_kinds": self.edge_kinds,
            "warnings": self.warnings,
        }


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _literal_from_metavars(metavars: dict) -> str | None:
    for value in metavars.values():
        content = str(value.get("abstract_content", ""))
        match = re.search(r'"([^"]+)"', content)
        if match:
            return match.group(1)
    return None


class CodeIndex:
    """One code.sqlite per project workspace."""

    SCHEMA_VERSION = SCHEMA_VERSION

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None

    @classmethod
    def for_repo(cls, repo_path) -> CodeIndex:
        ctx = ProjectContext.for_repo(repo_path)
        return cls(ctx.workspace / "code.sqlite")

    # ---- lifecycle ----------------------------------------------------

    def open(self) -> CodeIndex:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._ensure_schema()
        return self

    def close(self) -> None:
        if self._conn is not None:
            self._conn.commit()
            self._conn.close()
            self._conn = None

    def __enter__(self) -> Self:
        return self.open()

    def __exit__(self, *exc) -> None:
        self.close()

    @property
    def _db(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("code index is not open; call open() first")
        return self._conn

    def _ensure_schema(self) -> None:
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS meta ("
            " key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        row = self._db.execute(
            "SELECT value FROM meta WHERE key='schema_version'").fetchone()
        if row is None:
            self._create_schema()
            self._db.executemany(
                "INSERT INTO meta (key, value) VALUES (?, ?)",
                [("schema_version", str(self.SCHEMA_VERSION)),
                 ("created_at", "")])
        elif int(row[0]) != self.SCHEMA_VERSION:
            raise SchemaVersionMismatch(
                f"code.sqlite schema version {row[0]} != supported "
                f"{self.SCHEMA_VERSION}: regenerate the index")
        self._db.commit()

    def _create_schema(self) -> None:
        self._db.executescript(
            """
            CREATE TABLE files (
              id INTEGER PRIMARY KEY,
              path TEXT NOT NULL UNIQUE,
              language TEXT NOT NULL DEFAULT '',
              hash TEXT NOT NULL DEFAULT '',
              scan_run_id TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE symbols (
              id INTEGER PRIMARY KEY,
              file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
              kind TEXT NOT NULL,
              name TEXT NOT NULL,
              qualified_name TEXT NOT NULL,
              signature TEXT NOT NULL DEFAULT '',
              start_line INTEGER,
              end_line INTEGER,
              hash TEXT NOT NULL DEFAULT ''
            );
            CREATE UNIQUE INDEX symbols_unique ON symbols
              (file_id, kind, name, start_line);
            CREATE INDEX symbols_by_name ON symbols (name);
            CREATE INDEX symbols_by_qualified ON symbols (qualified_name);
            CREATE TABLE edges (
              id INTEGER PRIMARY KEY,
              source_id INTEGER NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
              target_id INTEGER NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
              kind TEXT NOT NULL,
              origin TEXT NOT NULL DEFAULT 'DETECTED',
              rule TEXT NOT NULL DEFAULT '',
              confidence TEXT NOT NULL DEFAULT 'high',
              scan_run_id TEXT NOT NULL,
              match_start INTEGER,
              match_end INTEGER
            );
            CREATE UNIQUE INDEX edges_unique ON edges
              (scan_run_id, source_id, target_id, kind, rule);
            CREATE INDEX edges_by_source ON edges (source_id);
            CREATE INDEX edges_by_target ON edges (target_id);
            CREATE INDEX edges_by_run ON edges (scan_run_id);
            """
        )

    # ---- ingestion (M2-B2 / M2-B3) ------------------------------------

    def ingest_astgrep(self, payload: str, scan_run_id: str,
                       scan_root: str | Path) -> IngestReport:
        """Ingest one ast-grep outline run (`scan --json=stream` NDJSON).

        Generation semantics: the index holds exactly one scan generation.
        Re-ingesting the same `scan_run_id` replaces its files and symbols;
        ingesting a *different* run id atomically retires the previous
        generation first, so facts of retired scans never survive (PR-2).
        """
        records: list[dict] = []
        try:
            for line in payload.splitlines():
                if line.strip():
                    records.append(json.loads(line))
        except (json.JSONDecodeError, AttributeError) as exc:
            raise IngestError(f"malformed ast-grep payload: {exc}") from exc

        report = IngestReport()
        db = self._db
        previous = self._meta_get("last_generation_run")
        if previous is not None and previous != scan_run_id:
            self._snapshot_previous()
        try:
            db.execute("BEGIN")
            if previous is not None and previous != scan_run_id:
                # New generation: retire everything (edges first, then
                # files — files cascade to symbols and their edges). The
                # retired generation stays queryable in code.prev.sqlite.
                db.execute("DELETE FROM edges")
                db.execute("DELETE FROM files")
                self._meta_set("previous_generation_run", previous)
            db.execute("DELETE FROM edges WHERE scan_run_id=?", (scan_run_id,))
            db.execute("DELETE FROM files WHERE scan_run_id=?", (scan_run_id,))
            for rec in records:
                try:
                    name = rec["text"]
                    rule_id = rec["ruleId"]
                    file_path = rec["file"]
                    line = int(rec["range"]["start"]["line"])
                    end = int(rec["range"].get("end", {}).get("line", line))
                    lines_text = str(rec.get("lines", ""))
                except (KeyError, TypeError, ValueError) as exc:
                    raise IngestError(f"incomplete ast-grep record: {exc}") from exc
                rel = self._relpath(file_path, scan_root)
                file_id = self._ensure_file(rel, str(rec.get("language", "")).lower(),
                                            _sha256(lines_text), scan_run_id)
                kind = rule_id.rsplit(".", 1)[-1]
                start_line = line + 1
                end_line = end + 1
                db.execute(
                    "INSERT OR IGNORE INTO symbols (file_id, kind, name,"
                    " qualified_name, start_line, end_line, hash)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (file_id, kind, name, f"{rel}::{name}@{start_line}",
                     start_line, end_line, _sha256(lines_text)))
                if db.execute("SELECT changes()").fetchone()[0]:
                    report.kinds[kind] = report.kinds.get(kind, 0) + 1
                    report.symbols += 1
            db.commit()
        except Exception:
            db.rollback()
            raise
        self._meta_set("last_generation_run", scan_run_id)
        report.files = db.execute(
            "SELECT COUNT(*) FROM files WHERE scan_run_id=?",
            (scan_run_id,)).fetchone()[0]
        self._rebuild_fts()
        db.commit()
        return report

    def ingest_semgrep(self, payload: str, scan_run_id: str,
                       scan_root: str | Path) -> IngestReport:
        """Ingest one Semgrep run (`scan --json`). Matches become edges from
        the containing symbol to a typed pseudo-symbol (endpoint, topic,
        datastore, http_client).

        Classification: the rule's `metadata.archskillkit` contract wins
        (SensorContract); rules without it go through the legacy bridge.
        Matches without a resolvable container symbol are reported as
        warnings and skipped."""
        try:
            document = json.loads(payload) if payload.strip() else {"results": []}
        except json.JSONDecodeError as exc:
            raise IngestError(f"malformed semgrep payload: {exc}") from exc
        if not isinstance(document, dict) or not isinstance(
            document.get("results", []), list
        ):
            raise IngestError("semgrep payload must be an object with results[]")

        report = IngestReport()
        db = self._db
        try:
            db.execute("BEGIN")
            db.execute("DELETE FROM edges WHERE scan_run_id=?", (scan_run_id,))
            for result in document.get("results", []):
                try:
                    check_id = result["check_id"]
                    path = result["path"]
                    line = int(result["start"]["line"])
                    end_line = int(result.get("end", {}).get("line", line))
                except (KeyError, TypeError, ValueError) as exc:
                    raise IngestError(f"incomplete semgrep result: {exc}") from exc

                extra = result.get("extra", {}) or {}
                metavars = extra.get("metavars", {}) or {}
                try:
                    contract = sensors.SensorContract.from_metadata(
                        check_id, extra.get("metadata"))
                except ContractError as exc:
                    report.warnings.append(f"invalid sensor contract: {exc}")
                    continue
                if contract is not None:
                    sensors.register(contract)
                    edge_kind, target_kind = contract.edge_kind, contract.target_kind
                    confidence = contract.confidence
                    target_name = None
                    if contract.target_metavar:
                        content = str(metavars.get(contract.target_metavar, {})
                                      .get("abstract_content", ""))
                        quoted = re.search(r'"([^"]+)"', content)
                        target_name = quoted.group(1) if quoted else (
                            content.strip() or None)
                    if target_name is None:
                        # literal scan across metavars (deprecated fallback)
                        target_name = _literal_from_metavars(metavars)
                    if target_name is None:
                        report.warnings.append(
                            f"contract target missing for {check_id}"
                            f" at {path}:{line}")
                        continue
                else:
                    legacy = sensors.classify_legacy(check_id)
                    if legacy is None:
                        report.warnings.append(
                            f"unknown check_id skipped: {check_id}")
                        continue
                    edge_kind, target_kind = legacy
                    confidence = "high"
                    target_name = _literal_from_metavars(metavars) or \
                        f"{target_kind}@{line}"

                rel = self._relpath(path, scan_root)
                file_row = self._file_by_path(rel)
                source = self._container_symbol(file_row, line,
                                                end_line) if file_row else None
                if source is None:
                    report.warnings.append(
                        f"no container symbol for {check_id} at {rel}:{line}")
                    continue
                target_id = self._ensure_symbol(
                    file_row, target_kind, target_name,
                    f"{rel}::{target_kind}:{target_name}@{line}", line)
                if self._db.execute("SELECT changes()").fetchone()[0]:
                    report.symbols += 1
                    report.kinds[target_kind] = \
                        report.kinds.get(target_kind, 0) + 1
                db.execute(
                    "INSERT OR IGNORE INTO edges (source_id, target_id, kind,"
                    " origin, rule, confidence, scan_run_id,"
                    " match_start, match_end)"
                    " VALUES (?, ?, ?, 'DETECTED', ?, ?, ?, ?, ?)",
                    (source["id"], target_id, edge_kind, check_id, confidence,
                     scan_run_id, line, end_line))
                if self._db.execute("SELECT changes()").fetchone()[0]:
                    report.edge_kinds[edge_kind] = \
                        report.edge_kinds.get(edge_kind, 0) + 1
                    report.edges += 1
            db.commit()
        except Exception:
            db.rollback()
            raise
        return report

    # ---- queries (M2-B4) ----------------------------------------------

    def search_symbol(self, query: str, limit: int = 20) -> list[dict]:
        tokens = [t for t in re.split(r"\W+", query) if t]
        if not tokens:
            return []
        match = " ".join(f'"{t}"*' for t in tokens)
        try:
            rows = self._db.execute(
                "SELECT s.*, fl.path AS path FROM symbols_fts"
                " JOIN symbols s ON s.id = symbols_fts.rowid"
                " JOIN files fl ON fl.id = s.file_id"
                " WHERE symbols_fts MATCH ?"
                " ORDER BY s.name LIMIT ?",
                (match, limit)).fetchall()
        except sqlite3.OperationalError:
            like = f"%{tokens[0]}%"
            rows = self._db.execute(
                "SELECT s.*, fl.path AS path FROM symbols s"
                " JOIN files fl ON fl.id = s.file_id"
                " WHERE s.name LIKE ? OR s.qualified_name LIKE ?"
                " ORDER BY s.name LIMIT ?", (like, like, limit)).fetchall()
        return [dict(r) for r in rows]

    def resolve(self, ref: str | int) -> dict:
        """Resolve an id, a qualified name (`path::name@line`), a
        `path::name` prefix, or a bare unique name."""
        if isinstance(ref, int):
            row = self._db.execute(
                "SELECT s.*, f.path AS path FROM symbols s JOIN files f"
                " ON f.id=s.file_id WHERE s.id=?", (ref,)).fetchone()
            if row is None:
                raise AmbiguousSymbolError(f"no symbol with id {ref}")
            return self._symbol_dict(row)
        base = ("SELECT s.*, f.path AS path FROM symbols s JOIN files f"
                " ON f.id=s.file_id WHERE ")
        for sql, param in (
            (base + "s.qualified_name=?", (str(ref),)),
            (base + "s.qualified_name LIKE ?", (f"{ref}@%",)),
            (base + "s.name=?", (str(ref),)),
        ):
            rows = self._db.execute(sql, param).fetchall()
            if len(rows) == 1:
                return self._symbol_dict(rows[0])
            if len(rows) > 1:
                candidates = [self._symbol_dict(r) for r in rows]
                raise AmbiguousSymbolError(
                    f"'{ref}' is ambiguous ({len(candidates)} candidates);"
                    " use a qualified name", candidates)
        raise AmbiguousSymbolError(f"no symbol matches '{ref}'")

    def outgoing(self, symbol_id: int) -> list[dict]:
        return self._edges(symbol_id, outgoing=True)

    def incoming(self, symbol_id: int) -> list[dict]:
        return self._edges(symbol_id, outgoing=False)

    def neighborhood(self, symbol_id: int, depth: int = 2,
                     max_nodes: int = 50) -> dict:
        adjacency, edge_list = self._adjacency()
        frontier = {symbol_id}
        seen = {symbol_id}
        for _ in range(max(0, depth)):
            nxt: set[int] = set()
            for node in frontier:
                for neighbor in adjacency.get(node, ()):
                    if neighbor not in seen:
                        nxt.add(neighbor)
            seen |= nxt
            frontier = nxt
            if len(seen) >= max_nodes:
                break
        kept = set(list(seen)[:max_nodes])
        return {
            "nodes": [self._symbol_dict(r) for r in self._rows(kept)],
            "edges": [e for e in edge_list
                      if e["source_id"] in kept and e["target_id"] in kept],
        }

    def path(self, src_id: int, dst_id: int) -> list[int] | None:
        """Shortest *directed* path (following edges source→target) as a
        list of symbol ids; None when no directed path exists. Inverse
        traversal needs `impact()` — PR-1 guards this contract."""
        if src_id == dst_id:
            return [src_id]
        adjacency = self._directed_adjacency()
        parents: dict[int, int] = {}
        queue = [src_id]
        visited = {src_id}
        while queue:
            node = queue.pop(0)
            for neighbor in adjacency.get(node, ()):
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                parents[neighbor] = node
                if neighbor == dst_id:
                    chain = [dst_id]
                    while chain[-1] != src_id:
                        chain.append(parents[chain[-1]])
                    return list(reversed(chain))
                queue.append(neighbor)
        return None

    def impact(self, symbol_id: int) -> list[dict]:
        """Everything that transitively reaches this symbol (reverse
        dependencies) — 'what breaks if this changes'."""
        _, edge_list = self._adjacency()
        reverse: dict[int, set[int]] = {}
        for e in edge_list:
            reverse.setdefault(e["target_id"], set()).add(e["source_id"])
        seen: set[int] = set()
        frontier = [symbol_id]
        while frontier:
            node = frontier.pop()
            for upstream in reverse.get(node, ()):
                if upstream not in seen and upstream != symbol_id:
                    seen.add(upstream)
                    frontier.append(upstream)
        return [self._symbol_dict(r) for r in self._rows(seen)]

    def stats(self) -> dict:
        def count(sql: str) -> int:
            return self._db.execute(sql).fetchone()[0]

        kinds = {
            row[0]: row[1] for row in self._db.execute(
                "SELECT kind, COUNT(*) FROM symbols GROUP BY kind ORDER BY kind")
        }
        edge_kinds = {
            row[0]: row[1] for row in self._db.execute(
                "SELECT kind, COUNT(*) FROM edges GROUP BY kind ORDER BY kind")
        }
        return {
            "files": count("SELECT COUNT(*) FROM files"),
            "symbols": count("SELECT COUNT(*) FROM symbols"),
            "edges": count("SELECT COUNT(*) FROM edges"),
            "kinds": kinds,
            "edge_kinds": edge_kinds,
        }

    def regenerate(self) -> None:
        """Drop all content; the index stays disposable by contract."""
        self._db.execute("DELETE FROM files")  # cascades to symbols
        self._db.execute("DELETE FROM edges")
        self._rebuild_fts()
        self._db.commit()

    def edges_of_run(self, scan_run_id: str) -> list[dict]:
        """All edges of a scan run with symbol/file context — the input
        the promotion services (M2-C1) turn into observations."""
        rows = self._db.execute(
            """
            SELECT e.kind AS kind, e.rule AS rule,
                   e.match_start AS match_start, e.match_end AS match_end,
                   ss.id AS source_id, ss.name AS source_name,
                   ss.start_line AS source_start_line,
                   sf.path AS source_path, ss.qualified_name AS source_qualified,
                   st.id AS target_id, st.name AS target_name,
                   st.kind AS target_kind,
                   tf.path AS target_path, st.qualified_name AS target_qualified
            FROM edges e
            JOIN symbols ss ON ss.id = e.source_id
            JOIN symbols st ON st.id = e.target_id
            JOIN files sf ON sf.id = ss.file_id
            JOIN files tf ON tf.id = st.file_id
            WHERE e.scan_run_id = ?
            ORDER BY e.id
            """,
            (scan_run_id,)).fetchall()
        return [dict(r) for r in rows]

    def files_of_run(self, scan_run_id: str) -> list[dict]:
        """All files of a scan run (path, language, content hash)."""
        rows = self._db.execute(
            "SELECT * FROM files WHERE scan_run_id=? ORDER BY path",
            (scan_run_id,)).fetchall()
        return [dict(r) for r in rows]

    def symbol_locations(self) -> set[tuple[str, int]]:
        """Every (path, start_line) the current index knows about — the
        freshness reference for stale-model detection (M2-F3)."""
        rows = self._db.execute(
            "SELECT f.path AS path, s.start_line AS start_line FROM symbols s"
            " JOIN files f ON f.id = s.file_id WHERE s.start_line IS NOT NULL")
        return {(r["path"], r["start_line"]) for r in rows}

    def previous_generation_run(self) -> str | None:
        return self._meta_get("previous_generation_run")

    def _snapshot_previous(self) -> None:
        """Copy the current database to code.prev.sqlite (generation
        rotation) — must run outside any transaction."""
        prev_path = self.db_path.with_name("code.prev.sqlite")
        if prev_path.exists():
            prev_path.unlink()
        self._db.execute("VACUUM INTO ?", (str(prev_path),))

    def diff_previous_generation(self) -> dict:
        """Semantic edge delta previous→current generation
        (docs/v2/46 F7) — the input for real architecture drift."""
        prev_run = self._meta_get("previous_generation_run")
        current = self._meta_get("last_generation_run")
        out = {"previous_generation": prev_run,
               "current_generation": current,
               "added": [], "removed": []}
        prev_path = self.db_path.with_name("code.prev.sqlite")
        if not prev_run or not current or not prev_path.exists():
            return out

        def keyset(rows) -> set[tuple[str, str, str, str]]:
            return {(r["kind"], r["source_qualified"],
                     r["target_qualified"], r["rule"]) for r in rows}

        prev_index = CodeIndex(prev_path).open()
        try:
            prev_keys = keyset(prev_index.edges_of_run(prev_run))
            cur_keys = keyset(self.edges_of_run(current))
            out["added"] = sorted(cur_keys - prev_keys)
            out["removed"] = sorted(prev_keys - cur_keys)
        finally:
            prev_index.close()
        return out

    def changed_files(self) -> list[str]:
        """Repo-relative paths changed between the previous generation
        snapshot and the current one — modified (content hash differs),
        added and removed files; sorted. Empty on the first generation.
        Deterministic input for context ranking (changed-file proximity,
        docs/v2/46 camino siguiente)."""
        prev_run = self._meta_get("previous_generation_run")
        current = self._meta_get("last_generation_run")
        prev_path = self.db_path.with_name("code.prev.sqlite")
        if not prev_run or not current or not prev_path.exists():
            return []
        prev_index = CodeIndex(prev_path).open()
        try:
            prev = {r["path"]: r["hash"]
                    for r in prev_index.files_of_run(prev_run)}
        finally:
            prev_index.close()
        current_files = {r["path"]: r["hash"]
                         for r in self.files_of_run(current)}
        changed = [p for p, h in current_files.items() if prev.get(p) != h]
        removed = [p for p in prev if p not in current_files]
        return sorted(changed + removed)

    def recent_delta_names(self) -> frozenset[str]:
        """Plain symbol names touched by the previous→current semantic
        edge delta (added + removed), parsed from the internal qualified
        format. Deterministic input for context ranking (recent graph
        delta). Empty on the first generation."""
        delta = self.diff_previous_generation()
        names: set[str] = set()
        for key in delta["added"] + delta["removed"]:
            for qualified in (key[1], key[2]):
                names.add(qualified.rsplit("::", 1)[-1].rsplit("@", 1)[0])
        return frozenset(names)

    # ---- internals ------------------------------------------------------

    def _relpath(self, path: str, scan_root: str | Path) -> str:
        pure = Path(path)
        if pure.is_absolute():
            try:
                return Path(os.path.relpath(path, scan_root)).as_posix()
            except ValueError:
                return path
        return pure.as_posix()

    def _ensure_file(self, rel: str, language: str, hash_: str,
                     scan_run_id: str) -> int:
        self._db.execute(
            "INSERT OR IGNORE INTO files (path, language, hash, scan_run_id)"
            " VALUES (?, ?, ?, ?)", (rel, language, hash_, scan_run_id))
        return self._file_by_path(rel)["id"]

    def _ensure_symbol(self, file_row: dict, kind: str, name: str,
                       qualified: str, line: int) -> int:
        self._db.execute(
            "INSERT OR IGNORE INTO symbols (file_id, kind, name,"
            " qualified_name, start_line, end_line, hash)"
            " VALUES (?, ?, ?, ?, ?, NULL, '')",
            (file_row["id"], kind, name, qualified, line))
        row = self._db.execute(
            "SELECT id FROM symbols WHERE file_id=? AND kind=? AND name=?"
            " AND start_line=?",
            (file_row["id"], kind, name, line)).fetchone()
        return row["id"]

    def _file_by_path(self, rel: str) -> dict | None:
        row = self._db.execute(
            "SELECT * FROM files WHERE path=?", (rel,)).fetchone()
        return dict(row) if row else None

    def _container_symbol(self, file_row: dict, match_start: int,
                          match_end: int | None = None) -> dict | None:
        """Smallest symbol range containing the semgrep match. Symbols
        without a stored end (old payloads) fall back to the legacy
        declaration-distance heuristic (≤ 2 lines)."""
        match_end = match_end or match_start
        rows = self._db.execute(
            "SELECT s.*, f.path AS path FROM symbols s JOIN files f"
            " ON f.id=s.file_id WHERE s.file_id=? AND s.start_line IS NOT NULL",
            (file_row["id"],)).fetchall()
        containing: list[tuple[int, int, str, sqlite3.Row]] = []
        nearby: list[tuple[int, int, str, sqlite3.Row]] = []
        for row in rows:
            start = row["start_line"] or 0
            end = row["end_line"] or start
            span = end - start
            if start <= match_start and match_end <= end:
                containing.append((span, 0 if row["kind"] == "function" else 1,
                                   row["name"], row))
                continue
            # transitional fallback: outline ranges that only cover the
            # declaration line cannot contain deep matches — keep the old
            # declaration-distance heuristic (≤ 2) for those.
            distance = abs(start - match_start)
            if distance <= 2:
                nearby.append((distance, 0 if row["kind"] == "function"
                               else 1, row["name"], row))
        pool = containing or nearby
        if not pool:
            return None
        pool.sort(key=lambda item: item[:3])
        return dict(pool[0][3])

    def _symbol_dict(self, row: sqlite3.Row) -> dict:
        return dict(row)

    def _rows(self, ids) -> list[sqlite3.Row]:
        ids = list(ids)
        if not ids:
            return []
        marks = ",".join("?" * len(ids))
        return self._db.execute(
            f"SELECT s.*, f.path AS path FROM symbols s JOIN files f"
            f" ON f.id=s.file_id WHERE s.id IN ({marks}) ORDER BY s.name",
            ids).fetchall()

    def _edges(self, symbol_id: int, outgoing: bool) -> list[dict]:
        join_col = "source_id" if outgoing else "target_id"
        rows = self._db.execute(
            f"""
            SELECT e.*, sf.path AS source_path, tf.path AS target_path,
                   ss.name AS source_name, st.name AS target_name,
                   st.kind AS target_kind, ss.kind AS source_kind
            FROM edges e
            JOIN symbols ss ON ss.id = e.source_id
            JOIN symbols st ON st.id = e.target_id
            JOIN files sf ON sf.id = ss.file_id
            JOIN files tf ON tf.id = st.file_id
            WHERE e.{join_col} = ?
            ORDER BY e.id
            """,
            (symbol_id,)).fetchall()
        return [dict(r) for r in rows]

    def _adjacency(self) -> tuple[dict[int, set[int]], list[dict]]:
        """Undirected adjacency — exploration only (`neighborhood`).
        Directed traversal MUST use `_directed_adjacency()` (PR-1)."""
        rows = self._db.execute(
            "SELECT id, source_id, target_id, kind, rule FROM edges").fetchall()
        edge_list = [dict(r) for r in rows]
        adjacency: dict[int, set[int]] = {}
        for e in edge_list:
            adjacency.setdefault(e["source_id"], set()).add(e["target_id"])
            adjacency.setdefault(e["target_id"], set()).add(e["source_id"])
        return adjacency, edge_list

    def _directed_adjacency(self) -> dict[int, set[int]]:
        rows = self._db.execute(
            "SELECT source_id, target_id FROM edges").fetchall()
        adjacency: dict[int, set[int]] = {}
        for src, dst in rows:
            adjacency.setdefault(src, set()).add(dst)
        return adjacency

    def _meta_get(self, key: str) -> str | None:
        row = self._db.execute(
            "SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def _meta_set(self, key: str, value: str) -> None:
        self._db.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))

    def _rebuild_fts(self) -> None:
        try:
            self._db.execute("DROP TABLE IF EXISTS symbols_fts")
            self._db.execute(
                "CREATE VIRTUAL TABLE symbols_fts USING fts5"
                "(name, qualified_name)")
            self._db.execute(
                "INSERT INTO symbols_fts (rowid, name, qualified_name)"
                " SELECT id, name, qualified_name FROM symbols")
        except sqlite3.OperationalError:
            pass  # FTS5 unavailable: search_symbol falls back to LIKE
