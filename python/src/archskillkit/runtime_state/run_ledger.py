"""RunLedger (ADR-0033): durable run summaries, deliberately outside
the ArchitectureWorld — the world event log records knowledge, never
runs or PIDs (M0 gate).

Contract: design/schemas/v2.4/run-record.yaml. The store is a seam:
SQLite is the default, an in-memory store backs the tests, and the
pending store spike (S24-02) can swap the backend without touching
consumers.
"""

from __future__ import annotations

import datetime as _dt
import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from archskillkit.ids import arch_state_root

RUN_RECORD_SCHEMA = "arch-skillkit/run-record-v1"

RunKind = Literal[
    "scan", "ingest", "discover", "drift", "project", "gate",
    "investigation", "simulation",
]
RunStatus = Literal["RUNNING", "PASS", "FAIL", "BLOCKED", "CANCELLED"]


def utcnow() -> str:
    return _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class RunRecord(BaseModel):
    """One pipeline execution summary (never a log dump)."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    kind: RunKind
    project_revision: str
    started_at: str
    status: RunStatus = "RUNNING"
    finished_at: str | None = None
    snapshot_before: str | None = None
    snapshot_after: str | None = None
    metrics: dict = Field(default_factory=dict)
    artifact_refs: list[str] = Field(default_factory=list)
    tool_revisions: list[str] = Field(default_factory=list)

    def canonical_json(self) -> str:
        return json.dumps(self.model_dump(), sort_keys=True,
                          separators=(",", ":"))


class LedgerError(ValueError):
    """Duplicate or unknown run id."""


class RunLedgerStore:
    """Minimal store seam (S24-02)."""

    def upsert(self, record: RunRecord) -> None: ...
    def get(self, run_id: str) -> RunRecord | None: ...
    def iter_newest_first(self) -> Iterator[RunRecord]: ...


class InMemoryRunLedgerStore(RunLedgerStore):
    def __init__(self) -> None:
        self._records: dict[str, RunRecord] = {}

    def upsert(self, record: RunRecord) -> None:
        self._records[record.run_id] = record

    def get(self, run_id: str) -> RunRecord | None:
        return self._records.get(run_id)

    def iter_newest_first(self) -> Iterator[RunRecord]:
        yield from sorted(self._records.values(),
                          key=lambda r: r.started_at, reverse=True)


class SqliteRunLedgerStore(RunLedgerStore):
    """One row per run: indexed columns for lookup, canonical JSON
    payload for the record body."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, isolation_level=None)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS runs ("
            " run_id TEXT PRIMARY KEY,"
            " status TEXT NOT NULL,"
            " started_at TEXT NOT NULL,"
            " payload TEXT NOT NULL)")

    def close(self) -> None:
        self._conn.close()

    def upsert(self, record: RunRecord) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO runs"
            " (run_id, status, started_at, payload) VALUES (?,?,?,?)",
            (record.run_id, record.status, record.started_at,
             record.model_dump_json()))

    def get(self, run_id: str) -> RunRecord | None:
        row = self._conn.execute(
            "SELECT payload FROM runs WHERE run_id = ?",
            (run_id,)).fetchone()
        return RunRecord(**json.loads(row[0])) if row else None

    def iter_newest_first(self) -> Iterator[RunRecord]:
        rows = self._conn.execute(
            "SELECT payload FROM runs ORDER BY started_at DESC, run_id")
        for (payload,) in rows:
            yield RunRecord(**json.loads(payload))


class RunLedger:
    """Append/finish run summaries. Idempotent finish; duplicate start
    of the same run_id is refused (runs are unique)."""

    def __init__(self, store: RunLedgerStore | None = None,
                 db_path: str | Path | None = None):
        if store is None:
            store = SqliteRunLedgerStore(
                db_path or arch_state_root() / "run-ledger.sqlite")
        self._store = store

    def start(self, record: RunRecord) -> RunRecord:
        if self._store.get(record.run_id) is not None:
            raise LedgerError(f"run id already exists: {record.run_id}")
        self._store.upsert(record)
        return record

    def finish(self, run_id: str, status: RunStatus, *,
               metrics: dict | None = None,
               artifact_refs: list[str] | None = None,
               snapshot_after: str | None = None) -> RunRecord:
        record = self._store.get(run_id)
        if record is None:
            raise LedgerError(f"unknown run id: {run_id}")
        record.status = status
        record.finished_at = utcnow()
        if metrics is not None:
            record.metrics = metrics
        if artifact_refs is not None:
            record.artifact_refs = artifact_refs
        if snapshot_after is not None:
            record.snapshot_after = snapshot_after
        self._store.upsert(record)
        return record

    def get(self, run_id: str) -> RunRecord:
        record = self._store.get(run_id)
        if record is None:
            raise LedgerError(f"unknown run id: {run_id}")
        return record

    def list(self, limit: int = 50, *,
             status: RunStatus | None = None) -> list[RunRecord]:
        out: list[RunRecord] = []
        for record in self._store.iter_newest_first():
            if status is not None and record.status != status:
                continue
            out.append(record)
            if len(out) >= limit:
                break
        return out
