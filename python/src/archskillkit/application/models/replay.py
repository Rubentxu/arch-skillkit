"""Replay fixture command DTOs (V2.5 M2, ADR-0049).

Schema-bound input/output for the ReplayApplicationService.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ReplayFixtureCommand(BaseModel):
    """Input for replaying a captured scanner-payload fixture."""

    model_config = ConfigDict(extra="forbid")

    fixture_dir: str = Field(description="Path to the fixture directory")
    write_golden: bool = Field(
        default=False,
        description="Overwrite golden.json with the replayed snapshot",
    )


class ReplayResult(BaseModel):
    """Replay verdict envelope (V2.4 M4 slice 19, docs/v2/56 §10)."""

    model_config = ConfigDict(extra="forbid")

    schema: str = "arch-skillkit/replay-fixture-result-v1"
    fixture_id: str
    fixture_dir: str
    replayed_snapshot_id: str
    golden_snapshot_id: str | None = None
    match: bool
    drift: dict[str, Any] | None = None
    pinned: dict[str, str] = Field(default_factory=dict)
    live_toolchain: dict[str, str] = Field(default_factory=dict)
