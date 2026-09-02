"""Agent bootstrap context (V2.4 M2, docs/v2/58 deliverable).

One call hands an agent everything it needs to start working on a
repository: a snapshot lease (AgentSession), the project status with
typed next actions, a budgeted context pack and the open knowledge
gaps. Read-only towards the world; the only state it creates is the
session lease in the runtime store (ADR-0033/0041).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from archskillkit.application.models.actions import ActionSuggestion
from archskillkit.application.models.snapshot import ArchitectureSnapshot
from archskillkit.application.queries.agent_session import (
    open_agent_session,
)
from archskillkit.application.queries.context_query import (
    ContextQuery,
    compile_context,
)
from archskillkit.application.queries.get_status import get_status
from archskillkit.context import ContextPack
from archskillkit.runtime_state.agent_sessions import (
    AgentSession,
    AgentSessionStore,
)

BOOTSTRAP_SCHEMA = "arch-skillkit/agent-bootstrap-v1"


class AgentBootstrap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema: Literal["arch-skillkit/agent-bootstrap-v1"] = (
        BOOTSTRAP_SCHEMA)  # type: ignore[assignment]
    project_id: str
    project_name: str
    root: str
    snapshot: ArchitectureSnapshot
    session: AgentSession
    suggestions: list[ActionSuggestion]
    context_pack: ContextPack
    open_gaps: list[dict] = Field(default_factory=list)


def bootstrap_agent(world, index=None, query: ContextQuery | None = None,
                    *, scope: dict | None = None,
                    budget: dict | None = None,
                    session_budget: dict | None = None,
                    store: AgentSessionStore | None = None,
                    ) -> AgentBootstrap:
    """Compile the agent's starting state in one deterministic shot.
    Without an explicit index, the workspace code index is opened for
    the call (an absent index degrades to an empty one, and status
    reports INDEX_MISSING instead of failing)."""
    own_index = index is None
    if own_index:
        from archskillkit.codeindex import CodeIndex

        index = CodeIndex(world.workspace / "code.sqlite").open()
    try:
        status = get_status(world, code_index=index)
        effective_query = query or ContextQuery(
            goal=f"project overview: {world.project_name}")
        pack = compile_context(_compiler_for(world, index),
                               effective_query)
        session = open_agent_session(world, index, scope=scope,
                                     budget=session_budget, store=store)
    finally:
        if own_index:
            index.close()
    return AgentBootstrap(
        project_id=world.project_id,
        project_name=world.project_name,
        root=world.root,
        snapshot=status.snapshot,
        session=session,
        suggestions=status.suggestions,
        context_pack=pack,
        open_gaps=world.knowledge_gaps(status="OPEN"),
    )


def _compiler_for(world, index):
    from archskillkit.context import ContextCompiler

    return ContextCompiler(world, index)
