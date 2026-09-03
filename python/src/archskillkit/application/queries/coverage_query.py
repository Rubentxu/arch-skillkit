"""Coverage and unknowns use case (V2.4 M5 slice 21).

Projects the knowledge summary from the snapshot: elements, relations,
evidence_coverage fraction, and unknowns count. This is a read model;
the snapshot is built deterministically from world state without
introducing new domain logic.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

COVERAGE_SCHEMA = "arch-skillkit/coverage-v1"


class CoverageResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema: Literal["arch-skillkit/coverage-v1"] = COVERAGE_SCHEMA  # type: ignore[assignment]
    elements: int
    relations: int
    evidence_coverage: float
    unknowns: int


def get_coverage(world, code_index=None) -> CoverageResult:
    """Project knowledge summary from the snapshot.

    ``code_index`` is accepted but not used at this layer — the caller
    is responsible for opening/closing it. Snapshot building handles
    the index internally.
    """
    # Build the snapshot to get the knowledge summary (same logic as
    # get_status, without the CLI-oriented suggestion layer).
    from archskillkit.application.queries.get_status import get_status

    result = get_status(world, code_index=code_index)
    snapshot = result.snapshot
    knowledge = snapshot.knowledge

    return CoverageResult(
        elements=knowledge.elements if knowledge else 0,
        relations=knowledge.relations if knowledge else 0,
        evidence_coverage=knowledge.evidence_coverage if knowledge else 0.0,
        unknowns=knowledge.unknowns if knowledge else 0,
    )
