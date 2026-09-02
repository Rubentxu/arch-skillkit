"""Typed action suggestions (ADR-0037 context, design/schemas/v2.4/
action-suggestion.yaml).

Suggestions are data, never executed implicitly: each one carries its
mutation scope and risk so a caller (CLI, MCP, Control Plane) can decide
and audit what running it would touch.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

MutationScope = Literal[
    "none", "runtime", "workspace", "proposal", "accepted-world"
]
Risk = Literal["low", "medium", "high"]


class ActionSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_id: str
    reason_code: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    preconditions: list[str] = Field(default_factory=list)
    mutation_scope: MutationScope
    risk: Risk
    expected_effects: list[str] = Field(default_factory=list)
