"""RuntimeRegistry (ADR-0033): tracks live arch-skillkit processes
under the XDG runtime directory — PIDs and commands belong HERE, never
in the world event log (M0 gate).

`cleanup_orphans` reaps entries whose PID is gone (best-effort: a
process death is detected with signal 0; an entry owned by another
user is kept — EPERM means it exists). Cross-process safety: every
read-modify-write holds an flock on the registry file and the body is
replaced atomically.
"""

from __future__ import annotations

import errno
import fcntl
import json
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from archskillkit.ids import arch_runtime_root
from archskillkit.runtime_state.run_ledger import utcnow

REGISTRY_VERSION = 1


class RuntimeEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pid: int
    started_at: str = ""
    run_id: str = ""
    project_id: str = ""
    command: str = ""


class RuntimeRegistry:
    def __init__(self, root: Path | None = None):
        self.root = root or arch_runtime_root()
        self.path = self.root / "registry.json"

    # ---- IO (locked, atomic) ------------------------------------------

    def _read_locked(self, fh) -> list[RuntimeEntry]:
        fh.seek(0)
        raw = fh.read().strip()
        if not raw:
            return []
        doc = json.loads(raw)
        return [RuntimeEntry(**e) for e in doc.get("entries", [])]

    def _write_locked(self, fh, entries: list[RuntimeEntry]) -> None:
        fh.seek(0)
        fh.truncate()
        fh.write(json.dumps({"version": REGISTRY_VERSION,
                             "entries": [e.model_dump() for e in entries]},
                            indent=2) + "\n")
        fh.flush()
        os.fsync(fh.fileno())

    def _mutate(self, fn):
        """Run fn(entries) under an exclusive lock, persisting the
        result atomically."""
        self.root.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a+") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                entries = fn(self._read_locked(fh))
                self._write_locked(fh, entries)
                return entries
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)

    # ---- API -----------------------------------------------------------

    def register(self, entry: RuntimeEntry) -> RuntimeEntry:
        if not entry.started_at:
            entry = entry.model_copy(update={"started_at": utcnow()})

        def add(entries: list[RuntimeEntry]) -> list[RuntimeEntry]:
            return [e for e in entries if e.pid != entry.pid] + [entry]

        self._mutate(add)
        return entry

    def unregister(self, pid: int) -> bool:
        removed: list[RuntimeEntry] = []

        def drop(entries: list[RuntimeEntry]) -> list[RuntimeEntry]:
            removed.extend(e for e in entries if e.pid == pid)
            return [e for e in entries if e.pid != pid]

        self._mutate(drop)
        return bool(removed)

    def active(self) -> list[RuntimeEntry]:
        """Registered entries, oldest first. Does not reap: call
        cleanup_orphans explicitly (cheap, but the caller decides)."""
        self.root.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            return []
        with open(self.path, "a+") as fh:
            fcntl.flock(fh, fcntl.LOCK_SH)
            try:
                return sorted(self._read_locked(fh),
                              key=lambda e: e.started_at)
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except OSError as exc:
            return exc.errno == errno.EPERM  # exists, not ours → alive
        return True

    def cleanup_orphans(self) -> list[RuntimeEntry]:
        """Remove entries whose PID is dead; returns what was removed."""
        removed: list[RuntimeEntry] = []

        def reap(entries: list[RuntimeEntry]) -> list[RuntimeEntry]:
            removed.extend(e for e in entries if not self._pid_alive(e.pid))
            return [e for e in entries if self._pid_alive(e.pid)]

        self._mutate(reap)
        return removed
