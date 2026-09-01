"""Projection metadata + lifecycle (design/schemas/projection-metadata.yaml,
docs/v2/35-projection-lifecycle.md).

A projection artifact always carries this sidecar: which source revision
produced it, how it was generated and whether it is stale or hand-edited.
"""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict

ProjectionStatus = Literal[
    "requested",
    "generated",
    "validated",
    "opened",
    "manually_modified",
    "stale",
    "superseded",
]


class ProjectionSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    architecture_run: str
    code_index_revision: str


class ProjectionMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ALLOWED_STATUSES: ClassVar[tuple] = ProjectionStatus.__args__  # type: ignore[attr-defined]

    schema_version: int = 1
    projection_id: str
    projection_type: str
    visual_intent: str
    source: ProjectionSource
    adapter_version: str
    status: ProjectionStatus = "generated"
    manually_modified: bool = False
    stale: bool = False
    artifact_path: str
    generated_sha256: str | None = None
