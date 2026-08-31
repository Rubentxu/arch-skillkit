"""arch-core pack — M2-A2 domain ontology.

Schemas follow design/schemas/*.yaml; the type and relation inventory
follows design/packs/arch-core.md. Only the object types modeled so far
(project, scan_run, observation, evidence, claim) declare full schemas;
decision/assumption/finding/review/artifact arrive with their milestones
(Phase C+). Behaviors (claim_evaluator, evidence_linker,
contradiction_detector, review_scheduler) are Phase C work and are
deliberately absent here.

Import-side effect contract: this module never registers global
ActiveGraph state — the pack symbol is inert until a runtime loads it.
"""

from __future__ import annotations

from typing import Literal

from activegraph.packs import ObjectType, Pack, RelationType
from pydantic import BaseModel, Field

Origin = Literal["DETECTED", "INFERRED", "DECLARED", "OBSERVED"]
Confidence = Literal["high", "medium", "low"]

ClaimStatus = Literal["proposed", "accepted", "rejected", "contradicted"]
ScanStatus = Literal["running", "success", "partial", "failed"]


class EvidenceData(BaseModel):
    """Provenance of a detection — design/schemas/observation.yaml#evidence."""

    tool: str
    rule: str = ""
    file: str = ""
    start_line: int | None = None
    end_line: int | None = None
    commit: str = ""


class ObservationData(BaseModel):
    """A deterministic fact extracted from the code — design/schemas/observation.yaml."""

    schema_version: int = 1
    origin: Origin = "DETECTED"
    confidence: Confidence = "high"
    subject: str
    predicate: str
    object: str
    evidence: EvidenceData


class ClaimData(BaseModel):
    """An architectural statement awaiting review — design/schemas/architecture-claim.yaml."""

    schema_version: int = 1
    origin: Origin = "INFERRED"
    confidence: Confidence = "medium"
    statement: str
    subjects: list[str] = Field(min_length=1)
    relations: list[str] = []
    evidence_refs: list[str] = []
    contradiction_refs: list[str] = []
    status: ClaimStatus = "proposed"


class ProjectData(BaseModel):
    """The analyzed repository this world belongs to."""

    project_id: str
    name: str
    root: str
    remote: str = ""
    created_at: str = ""


class ScanRunData(BaseModel):
    """One deterministic scanner execution (V1 scan.sh or future ingestor)."""

    scan_id: str
    status: ScanStatus = "running"
    started_at: str = ""
    finished_at: str = ""
    tools: dict[str, str] = Field(default_factory=dict)


class FindingData(BaseModel):
    """A deterministic reviewer/drift finding (docs/v2/04, M2-C4, M2-F1)."""

    kind: Literal["unsupported_claim", "contradiction", "missing_evidence",
                  "stale_evidence", "architecture_drift"]
    severity: Confidence = "medium"
    target_id: str = ""
    detail: str = ""


class ReviewData(BaseModel):
    """One reviewer pass over the world (M2-C4)."""

    reviewed_at: str = ""
    summary: str = ""
    findings_count: int = 0


def _relation(name: str, source: tuple[str, ...] = (), target: tuple[str, ...] = (),
              description: str = "") -> RelationType:
    return RelationType(name=name, source_types=source, target_types=target,
                        description=description)


ARCH_CORE_OBJECT_TYPES = (
    "project", "scan_run", "observation", "evidence", "claim",
    "finding", "review",
)

# design/packs/arch-core.md relation inventory. Endpoints are pinned only
# where the design pins them (evidenced_by/supports/contradicts); the rest
# stay open until their owning milestones give them semantics.
ARCH_CORE_RELATION_TYPES = (
    "supports", "contradicts", "evidenced_by",
    "derived_from", "validates", "invalidates", "supersedes",
)

pack = Pack(
    name="arch_core",
    version="0.2.0",
    description="ArchSkillKit core ontology: evidence, observations, claims and findings.",
    object_types=(
        ObjectType(name="project", schema=ProjectData,
                   description="The analyzed repository."),
        ObjectType(name="scan_run", schema=ScanRunData,
                   description="One deterministic scanner execution."),
        ObjectType(name="observation", schema=ObservationData,
                   description="A deterministic fact extracted from the code."),
        ObjectType(name="evidence", schema=EvidenceData,
                   description="Provenance backing an observation or claim."),
        ObjectType(name="claim", schema=ClaimData,
                   description="An architectural statement awaiting review."),
        ObjectType(name="finding", schema=FindingData,
                   description="A deterministic reviewer finding."),
        ObjectType(name="review", schema=ReviewData,
                   description="One reviewer pass over the world."),
    ),
    relation_types=(
        _relation("evidenced_by", source=("claim",), target=("evidence",),
                  description="A claim is backed by evidence."),
        _relation("supports", source=("evidence", "observation"), target=("claim",),
                  description="Evidence or an observation supports a claim."),
        _relation("contradicts", source=("observation", "claim"), target=("claim",),
                  description="Contradicting input — blocks silent promotion."),
        _relation("derived_from"),
        _relation("validates"),
        _relation("invalidates"),
        _relation("supersedes"),
    ),
)
