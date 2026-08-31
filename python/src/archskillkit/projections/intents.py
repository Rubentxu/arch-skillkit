"""VisualIntent — semantic description of what to communicate (docs/v2/26).

Agents express intent, never tool names; the router decides the format.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

IntentType = Literal[
    "architecture",
    "exploration",
    "technical_diagram",
    "knowledge_map",
    "dependency_graph",
    "large_graph_analysis",
    "proposal_board",
    "investigation",
]

Audience = Literal["engineer", "architect", "product", "external"]
Interaction = Literal["view", "exploratory", "edit"]
Detail = Literal["low", "medium", "high"]


class IntentScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    depth: int | None = None


class VisualIntent(BaseModel):
    """Attributes follow docs/v2/26-visual-intent-spec.md."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    type: IntentType
    subject: str
    scope: IntentScope = IntentScope()
    audience: Audience = "engineer"
    interaction: Interaction = "exploratory"
    detail: Detail = "medium"
    editable: bool = False
    layout_hint: str | None = None
    include_evidence: bool = False
    include_notes: bool = False
