"""AgentSession — version lease for agent work (V2.4 ADR-0041,
design/schemas/v2.4/agent-session.yaml).

A session leases a specific snapshot (world revision + code generation
+ policy revision). Any of those moving on invalidates the lease:
`detect_stale` marks ACTIVE sessions STALE deterministically. Sessions
are runtime coordination state — they live under the XDG runtime root,
never in the world event log (ADR-0033).
"""

from __future__ import annotations

import fcntl
import json
import os
import uuid
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from archskillkit.ids import arch_runtime_root
from archskillkit.runtime_state.run_ledger import utcnow

SESSION_SCHEMA = "arch-skillkit/agent-session-v1"

SessionStatus = Literal["ACTIVE", "STALE", "CLOSED"]


class AgentSession(BaseModel):
    """No `schema` field: like ViewerDescriptor, this is a contract
    object matching the design schema exactly (additionalProperties:
    false); wire outputs carry their schema id in an envelope."""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    snapshot_id: str
    world_revision: str
    code_generation: str
    policy_revision: str
    scope: dict = Field(default_factory=dict)
    budget: dict = Field(default_factory=dict)
    status: SessionStatus = "ACTIVE"
    created_at: str = ""

    def is_current(self, snapshot) -> bool:
        """The lease holds only while every leased revision matches."""
        return (
            self.status == "ACTIVE"
            and self.world_revision == snapshot.world_revision.event_id
            and self.code_generation == snapshot.code_revision.generation
            and self.policy_revision == snapshot.policy_revision
        )


class AgentSessionStore:
    def __init__(self, root: Path | None = None):
        self.root = root or arch_runtime_root()
        self.path = self.root / "agent-sessions.json"

    # ---- locked, atomic IO (same pattern as RuntimeRegistry) ----------

    def _read_locked(self, fh) -> dict[str, AgentSession]:
        fh.seek(0)
        raw = fh.read().strip()
        if not raw:
            return {}
        doc = json.loads(raw)
        return {s["session_id"]: AgentSession(**s)
                for s in doc.get("sessions", [])}

    def _write_locked(self, fh, sessions: dict[str, AgentSession]) -> None:
        fh.seek(0)
        fh.truncate()
        fh.write(json.dumps(
            {"version": 1,
             "sessions": [s.model_dump() for s in sessions.values()]},
            indent=2) + "\n")
        fh.flush()
        os.fsync(fh.fileno())

    def _mutate(self, fn):
        self.root.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a+") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                sessions = fn(self._read_locked(fh))
                self._write_locked(fh, sessions)
                return sessions
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)

    # ---- API -----------------------------------------------------------

    def open(self, snapshot, scope: dict | None = None,
             budget: dict | None = None,
             session_id: str | None = None) -> AgentSession:
        """Lease the given snapshot's revisions (ARCHITECTURE — an
        application-layer snapshot, not the world dict projection)."""
        session = AgentSession(
            session_id=session_id or f"sess-{uuid.uuid4().hex[:12]}",
            snapshot_id=snapshot.snapshot_id,
            world_revision=snapshot.world_revision.event_id,
            code_generation=snapshot.code_revision.generation,
            policy_revision=snapshot.policy_revision,
            scope=dict(scope or {}),
            budget=dict(budget or {}),
            status="ACTIVE",
            created_at=utcnow(),
        )

        def put(sessions: dict[str, AgentSession]) -> dict[str, AgentSession]:
            sessions[session.session_id] = session
            return sessions

        self._mutate(put)
        return session

    def get(self, session_id: str) -> AgentSession | None:
        self.root.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            return None
        with open(self.path, "a+") as fh:
            fcntl.flock(fh, fcntl.LOCK_SH)
            try:
                return self._read_locked(fh).get(session_id)
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)

    def list(self, status: str | None = None) -> list[AgentSession]:
        sessions = sorted(self._mutate(lambda s: s).values(),
                          key=lambda s: s.created_at)
        if status is not None:
            sessions = [s for s in sessions if s.status == status]
        return sessions

    def close(self, session_id: str) -> bool:
        closed: list[AgentSession] = []

        def mark(sessions: dict[str, AgentSession]) -> dict[str, AgentSession]:
            session = sessions.get(session_id)
            if session and session.status != "CLOSED":
                session = session.model_copy(
                    update={"status": "CLOSED"})
                sessions[session_id] = session
                closed.append(session)
            return sessions

        self._mutate(mark)
        return bool(closed)

    def detect_stale(self, current_snapshot) -> list[AgentSession]:
        """Mark every ACTIVE session whose leased revisions no longer
        match the current snapshot; returns what went STALE."""
        staled: list[AgentSession] = []

        def mark(sessions: dict[str, AgentSession]) -> dict[str, AgentSession]:
            for key, session in sessions.items():
                if session.status == "ACTIVE" \
                        and not session.is_current(current_snapshot):
                    staled.append(session)
                    sessions[key] = session.model_copy(
                        update={"status": "STALE"})
            return sessions

        self._mutate(mark)
        return staled
