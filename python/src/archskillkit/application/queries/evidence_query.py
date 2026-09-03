"""Evidence and provenance use case (V2.4 M5 slice 21).

Returns all evidence objects with their claim links. This is a read model:
nothing here mutates the world.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EVIDENCE_SCHEMA = "arch-skillkit/evidence-v1"


class EvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    tool: str
    rule: str = ""
    file: str = ""
    start_line: int | None = None
    end_line: int | None = None
    commit: str = ""
    claim_ids: list[str] = Field(default_factory=list)


class EvidenceResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema: Literal["arch-skillkit/evidence-v1"] = EVIDENCE_SCHEMA  # type: ignore[assignment]
    count: int
    items: list[EvidenceItem]


def get_evidence(world) -> EvidenceResult:
    """Project all evidence objects and their claim links.

    An evidence object may be linked from zero or more claims; those
    claim ids are listed in ``claim_ids`` so the UI can show
    provenance without duplicating claim logic here.
    """
    items: list[EvidenceItem] = []
    seen: set[str] = set()

    for ev in world.find_objects("evidence"):
        ev_id = ev["id"]
        if ev_id in seen:
            continue
        seen.add(ev_id)
        data = ev["data"]
        # Collect claim ids that reference this evidence
        claim_refs = [
            c["id"]
            for c in world.find_objects("claim")
            if ev_id in (c["data"].get("evidence_refs") or [])
        ]
        items.append(
            EvidenceItem(
                id=ev_id,
                tool=data.get("tool", ""),
                rule=data.get("rule", ""),
                file=data.get("file", ""),
                start_line=data.get("start_line"),
                end_line=data.get("end_line"),
                commit=data.get("commit", ""),
                claim_ids=claim_refs,
            )
        )

    return EvidenceResult(count=len(items), items=items)
