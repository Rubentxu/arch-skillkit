"""AgentSession use case (V2.4 M2, ADR-0041): open a session lease
against the current snapshot, check it, and detect staleness.

The lease is derived from an ArchitectureSnapshot (revisions only), so
opening a session never writes to the world. Detection marks stale
leases deterministically: any of world/code/policy moving invalidates.
"""

from __future__ import annotations

from archskillkit.application.snapshot_builder import build_snapshot
from archskillkit.runtime_state.agent_sessions import (
    AgentSession,
    AgentSessionStore,
)


def open_agent_session(world, code_index=None, *,
                       scope: dict | None = None,
                       budget: dict | None = None,
                       store: AgentSessionStore | None = None,
                       ) -> AgentSession:
    """Lease the current revisions of an open world. Detects staleness
    of pre-existing sessions for free: any ACTIVE lease older than this
    snapshot goes STALE."""
    snapshot = build_snapshot(world, code_index)
    store = store or AgentSessionStore()
    store.detect_stale(snapshot)
    return store.open(snapshot, scope=scope, budget=budget)


def session_is_current(session: AgentSession, world, code_index=None,
                       store: AgentSessionStore | None = None,
                       ) -> bool:
    """Re-check a lease against the current revisions."""
    snapshot = build_snapshot(world, code_index)
    store = store or AgentSessionStore()
    store.detect_stale(snapshot)
    refreshed = store.get(session.session_id)
    if refreshed is None:
        return False
    return refreshed.status == "ACTIVE" and refreshed.is_current(snapshot)
