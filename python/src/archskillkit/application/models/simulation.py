"""Simulation command DTOs (V2.5 M2, ADR-0049).

Schema-bound input/output for the SimulationApplicationService.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class SimulationCommand(BaseModel):
    """Input for a counterfactual simulation."""

    model_config = ConfigDict(extra="forbid")

    verb: Literal["relation_add", "move", "delete"] = Field(
        description="What counterfactual to apply"
    )
    source: str | None = Field(
        default=None, description="Source element name (relation_add verb)"
    )
    target: str | None = Field(
        default=None, description="Target element name (relation_add verb)"
    )
    kind: str = Field(
        default="depends_on",
        description="Relation kind (relation_add verb; default: depends_on)",
    )
    element: str | None = Field(
        default=None, description="Element name (move/delete verbs)"
    )
    to: str | None = Field(
        default=None, description="Target category (move verb)"
    )


class SimulationResult(BaseModel):
    """Counterfactual simulation outcome (docs/v2/57 §8)."""

    model_config = ConfigDict(extra="forbid")

    schema: Literal["arch-skillkit/simulation-result-v1"] = "arch-skillkit/simulation-result-v1"
    verb: Literal["relation_add", "move", "delete"]
    base_snapshot_id: str
    base_snapshot_after_id: str
    base_unchanged: bool
    fork_id: str
    applied_to_fork: dict[str, Any] = Field(default_factory=dict)
    delta: dict[str, list[str]] = Field(default_factory=dict)
    policy_result: dict[str, Any] = Field(default_factory=dict)
    blast_radius: list[str] = Field(default_factory=list)
    unknowns_opened: list[str] = Field(default_factory=list)
    recommendation: Literal["allowed", "risky", "blocked", "unknown"]
    project_id: str
