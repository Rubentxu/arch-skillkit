"""arch-model pack — architecture elements and their typed relations
(design/packs/arch-model.md, docs/v2/04-activegraph-domain-model.md).

Representation note (ADR-0024 boundary): ArchitectureRelation is modeled
as a typed ActiveGraph edge between architecture elements, with its
evidence links carried in the edge data. The object-level view the docs
describe is provided by the domain API (world.architecture_relations),
not by the runtime — swapping this representation stays inside the
encapsulation boundary.
"""

from __future__ import annotations

from typing import Literal

from activegraph.packs import ObjectType, Pack, RelationType
from pydantic import BaseModel

from archskillkit.packs.arch_core import Confidence, Origin

ElementCategory = Literal[
    "system",
    "container",
    "component",
    "bounded_context",
    "external_system",
    "datastore",
    "topic",
    "interface",
]


class ArchitectureElementData(BaseModel):
    name: str
    kind: ElementCategory
    origin: Origin = "DETECTED"
    confidence: Confidence = "high"
    summary: str = ""


class ArchitectureRuleData(BaseModel):
    """A structured boundary rule evaluated WITHOUT an LLM (ADR-0022):
    `source_category -[forbidden_relation]-> target_category` is drift."""

    name: str
    statement: str
    forbidden_relation: str
    source_category: str
    target_category: str
    severity: Confidence = "high"


ProposalStatus = Literal["open", "approved", "rejected", "promoted"]


class ProposalData(BaseModel):
    """An architectural proposal living in a forked run (docs/v2/08).
    Promotion into the main world requires status == approved (UAT2-014)."""

    name: str
    status: ProposalStatus = "open"
    rationale: str = ""
    fork_run: str = ""
    created_at: str = ""


def _relation(name: str, source: tuple[str, ...] = (), target: tuple[str, ...] = (),
              description: str = "") -> RelationType:
    return RelationType(name=name, source_types=source, target_types=target,
                        description=description)


ARCH_MODEL_OBJECT_TYPES = ("architecture_element", "architecture_rule", "proposal")

ARCH_MODEL_RELATION_TYPES = (
    "exposes", "consumes", "depends_on", "realizes",
    "belongs_to", "reads", "writes", "publishes",
)

pack = Pack(
    name="arch_model",
    version="0.3.0",
    description="ArchSkillKit architecture elements, rules, proposals and relations.",
    object_types=(
        ObjectType(name="architecture_element", schema=ArchitectureElementData,
                   description="A curated architectural building block."),
        ObjectType(name="architecture_rule", schema=ArchitectureRuleData,
                   description="A deterministic boundary rule (drift detector input)."),
        ObjectType(name="proposal", schema=ProposalData,
                   description="An architectural proposal on a forked run."),
    ),
    relation_types=(
        # Endpoints are typed at the object level ('architecture_element');
        # the finer element categories (docs/v2/04) live in data.kind and
        # are enforced by the domain layer, not by the runtime.
        _relation("exposes", source=("architecture_element",),
                  target=("architecture_element",),
                  description="A component exposes an external interface."),
        _relation("consumes", source=("architecture_element",),
                  target=("architecture_element",),
                  description="A component consumes messages from a topic."),
        _relation("depends_on", source=("architecture_element",),
                  target=("architecture_element",),
                  description="A component depends on another element."),
        _relation("realizes", source=("architecture_element",),
                  target=("architecture_element",),
                  description="A component realizes an abstraction."),
        _relation("belongs_to", source=("architecture_element",),
                  target=("architecture_element",),
                  description="Containment within a larger element."),
        _relation("reads", source=("architecture_element",),
                  target=("architecture_element",)),
        _relation("writes", source=("architecture_element",),
                  target=("architecture_element",)),
        _relation("publishes", source=("architecture_element",),
                  target=("architecture_element",),
                  description="A component publishes messages to a topic."),
    ),
)
