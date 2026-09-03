"""Knowledge gaps use case (V2.4 M5 slice 21).

Lists knowledge gaps, optionally filtered by status. This is a read model.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

GAPS_SCHEMA = "arch-skillkit/gaps-v1"

# Valid status values per arch_model pack (GapStatus).
VALID_GAP_STATUSES: frozenset[str] = frozenset({"OPEN", "INVESTIGATING", "RESOLVED", "DEFERRED"})


class GapsResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema: Literal["arch-skillkit/gaps-v1"] = GAPS_SCHEMA  # type: ignore[assignment]
    count: int
    gaps: list[dict] = Field(default_factory=list)


class InvalidGapStatus(ValueError):
    """Returned when ?status= is not one of the valid GapStatus values."""

    code: str = "INVALID_STATUS"
    message: str = ""

    def __init__(self, status: str) -> None:
        self.message = (
            f"invalid status {status!r}; accepted: {', '.join(sorted(VALID_GAP_STATUSES))}"
        )
        super().__init__(self.message)


def get_knowledge_gaps(world, *, status: str | None = None) -> GapsResult:
    """List knowledge gaps, optionally filtered by status.

    Args:
        world: open ArchitectureWorld
        status: if given, must be one of the valid GapStatus values.
                Raises InvalidGapStatus if not.

    Raises:
        InvalidGapStatus: ``status`` is set to an unrecognized value.
    """
    if status is not None and status not in VALID_GAP_STATUSES:
        raise InvalidGapStatus(status)

    gaps = world.knowledge_gaps(status=status)
    return GapsResult(count=len(gaps), gaps=gaps)
