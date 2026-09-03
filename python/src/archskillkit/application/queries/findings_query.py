"""Governance findings use case (V2.4 M5 slice 21).

Returns persisted review/drift findings from the world. This is a
read model; findings are produced by the governance policy engine.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

FINDINGS_SCHEMA = "arch-skillkit/findings-v1"


class FindingsResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema: Literal["arch-skillkit/findings-v1"] = FINDINGS_SCHEMA  # type: ignore[assignment]
    count: int
    findings: list[dict] = Field(default_factory=list)


def get_findings(world) -> FindingsResult:
    """Project all governance findings from the world."""
    findings = world.findings()
    return FindingsResult(count=len(findings), findings=findings)
