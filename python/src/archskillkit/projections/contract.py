"""ProjectionAdapter contract (docs/v2/27 + design/projections/*.yaml).

Adapters convert internal knowledge into an external file format. The
domain knows only this contract — never the applications themselves.
"""

from __future__ import annotations

from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from archskillkit.projections.intents import IntentType, VisualIntent

Format = Literal[
    "likec4", "arrows", "drawio", "jsoncanvas", "graphml",
]


class ProjectionContext(BaseModel):
    """References, not duplicated state (docs/v2/27)."""

    model_config = ConfigDict(extra="forbid")

    project_id: str
    architecture_run: str
    code_index_revision: str
    evidence_refs: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    annotations: dict[str, Any] = Field(default_factory=dict)


class ProjectionMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nodes: int
    edges: int
    generated_at: str = ""


class ProjectionResult(BaseModel):
    """design/projections/projection-result.yaml — every result must carry
    the source snapshot it was generated from (invariant 3, docs/v2/27)."""

    model_config = ConfigDict(extra="forbid")

    format: str
    path: str
    source_snapshot: dict[str, str]
    status: str = "generated"
    warnings: list[str] = Field(default_factory=list)
    metrics: ProjectionMetrics


@runtime_checkable
class ProjectionAdapter(Protocol):
    """Common adapter contract — docs/v2/27-projection-contract.md."""

    name: str
    supported_intents: frozenset[IntentType]
    version: str

    def project(
        self, intent: VisualIntent, context: ProjectionContext
    ) -> ProjectionResult: ...
