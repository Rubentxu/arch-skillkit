"""ArchitectureSnapshot V2.4 (ADR-0033, design/schemas/v2.4/
architecture-snapshot.yaml).

A compact manifest of *revisions*, never a copy of the graph. The same
event log and code generation always produce the same digest (M0 gate:
"snapshot reproducible para mismo event log/generation"). PID and other
runtime state are deliberately absent — they belong to the
RuntimeRegistry (ADR-0033), not to this manifest.
"""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SNAPSHOT_SCHEMA = "arch-skillkit/architecture-snapshot-v1"


class ProjectRevision(BaseModel):
    """Which state of the analyzed repository produced this snapshot."""

    model_config = ConfigDict(extra="forbid")

    git_commit: str
    dirty_digest: str | None = None


class CodeRevision(BaseModel):
    """Code Index state: one scan generation plus sensor rule revisions."""

    model_config = ConfigDict(extra="forbid")

    generation: str
    sensor_revisions: list[str] = Field(default_factory=list)


class WorldRevision(BaseModel):
    """Event-log position (ADR-0015): last event id + projection digest."""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    digest: str


class KnowledgeSummary(BaseModel):
    """Counts plus the M0 coverage baseline. `evidence_coverage` is the
    fraction of architecture elements backed by an accepted claim
    (accepted ⟹ evidenced, per promotion rules); `unknowns` counts the
    rest. 0.0 coverage on an empty world means "nothing measured yet",
    not a measured zero."""

    model_config = ConfigDict(extra="forbid")

    elements: int = Field(ge=0)
    relations: int = Field(ge=0)
    evidence_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    unknowns: int = Field(default=0, ge=0)


class ArchitectureSnapshot(BaseModel):
    # `schema` is the wire name from the design schema; the pydantic
    # attribute shadows BaseModel.schema (deprecated in v2) on purpose.
    model_config = ConfigDict(extra="forbid")

    schema: Literal["arch-skillkit/architecture-snapshot-v1"] = SNAPSHOT_SCHEMA  # type: ignore[assignment]
    snapshot_id: str = ""
    project_revision: ProjectRevision
    code_revision: CodeRevision
    world_revision: WorldRevision
    policy_revision: str
    knowledge: KnowledgeSummary | None = None
    artifact_manifest_digest: str | None = None

    def canonical_json(self) -> str:
        """Deterministic serialization: sorted keys, compact separators."""
        return json.dumps(self.model_dump(), sort_keys=True,
                          separators=(",", ":"))

    def digest(self) -> str:
        """Stable digest of the snapshot *content* (snapshot_id excluded
        to avoid the circular dependency)."""
        return snapshot_digest(self)

    def with_snapshot_id(self) -> ArchitectureSnapshot:
        """Return a copy with snapshot_id derived from the content
        digest: `snap-<first 16 hex chars>`."""
        return self.model_copy(
            update={"snapshot_id": f"snap-{self.digest()[:16]}"})


def snapshot_digest(snapshot: ArchitectureSnapshot) -> str:
    payload = snapshot.model_dump(exclude={"snapshot_id"})
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
