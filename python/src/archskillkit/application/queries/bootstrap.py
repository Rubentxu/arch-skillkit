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

    The ``index`` parameter is required — the caller (delivery layer) opens
    the CodeIndex and passes the open instance. Passing ``None`` signals
    "no index available" (ARC-005: application must not instantiate
    CodeIndex); status will report INDEX_MISSING and a minimal context pack
    is returned rather than a code-enriched one.
    """
    status = get_status(world, code_index=index)
    effective_query = query or ContextQuery(
        goal=f"project overview: {world.project_name}")
    if index is None:
        # ARC-005: cannot instantiate CodeIndex in application layer.
        # Return a minimal pack without code enrichment; status carries
        # the INDEX_MISSING suggestion so the caller knows to run discover.
        pack = ContextPack(goal=effective_query.goal, intent="overview")
    else:
        pack = compile_context(_compiler_for(world, index), effective_query)
    session = open_agent_session(world, index, scope=scope,
                                 budget=session_budget, store=store)
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
