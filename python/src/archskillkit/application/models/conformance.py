"""Conformance mining command DTOs (V2.5 M2, ADR-0049).

Schema-bound input/output for the ConformanceApplicationService.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MineConformanceCommand(BaseModel):
    """Input for the Conformance Miner."""

    model_config = ConfigDict(extra="forbid")

    min_support: int = Field(
        default=3,
        ge=1,
        description="Minimum occurrence count for a pattern to become a candidate (default: 3)",
    )


class MineConformanceResult(BaseModel):
    """Conformance mining result envelope."""

    model_config = ConfigDict(extra="forbid")

    schema: str = "arch-skillkit/conformance-mining-v1"
    project_id: str
    min_support: int
    candidates: list[dict[str, Any]] = Field(default_factory=list)
