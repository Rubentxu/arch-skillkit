"""Conformance Miner — identifies repeated architectural patterns (V2.4 M6 slice 30).

Scans the live architecture graph for relation-kind triples
``(rel_kind, source_kind, target_kind)`` that appear with sufficient
support, and proposes them as ``ArchitectureRuleCandidate`` objects
that require human / policy approval before becoming live rules.

The miner is **read-only**: it never mutates the world.  Relations
whose endpoint elements carry no ``kind`` are silently skipped.

Schema: ``arch-skillkit/rule-candidate-v1``
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from archskillkit.world import ArchitectureWorld


class ProposedRule(BaseModel):
    """DRAFT rule pre-filled from the observed pattern.

    The operator edits this before approving.  The statement explicitly
    marks it as a draft awaiting approval.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Rule name (derived from candidate_id)")
    statement: str = Field(description="DRAFT — requires human/policy approval before activation")
    forbidden_relation: str = Field(description="Relation kind that is forbidden")
    source_category: str = Field(description="Source element kind")
    target_category: str = Field(description="Target element kind")
    severity: Literal["low", "medium", "high"] = Field(
        default="medium", description="Severity when rule is violated"
    )


class ArchitectureRuleCandidate(BaseModel):
    """A repeated architectural pattern elevated to rule-candidate status.

    Schema: ``arch-skillkit/rule-candidate-v1``
    """

    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(description="Deterministic slug: <relkind>-<sourcekind>-<targetkind>")
    rel_kind: str = Field(description="Kind of the repeated relation")
    source_kind: str = Field(description="Kind of the source architecture element")
    target_kind: str = Field(description="Kind of the target architecture element")
    support: int = Field(ge=1, description="Number of occurrences of this pattern")
    example_relation_ids: list[str] = Field(
        default_factory=list, description="Up to 5 relation IDs showing this pattern (sorted)"
    )
    observed_in_runs: list[str] = Field(
        default_factory=list, description="Distinct run IDs where the pattern was observed (sorted)"
    )
    status: Literal["candidate", "approved", "rejected"] = Field(
        default="candidate",
        description="Lifecycle status — starts as 'candidate'; "
        "human/policy approval transitions to 'approved' or 'rejected'",
    )
    proposed_rule: ProposedRule = Field(
        description="Pre-filled rule that the operator edits before approving"
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _kind_of(world: ArchitectureWorld, element_id: str) -> str | None:
    """Return the ``kind`` field of an architecture element, or None if unknown."""
    try:
        obj = world.get_object(element_id)
    except KeyError:
        return None
    if obj.get("type") != "architecture_element":
        return None
    return obj.get("data", {}).get("kind")


def _candidate_id(rel_kind: str, source_kind: str, target_kind: str) -> str:
    """Deterministic slug for a pattern triple."""
    return f"{rel_kind}-{source_kind}-{target_kind}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def mine(world: ArchitectureWorld, *, min_support: int = 3) -> list[ArchitectureRuleCandidate]:
    """Scan ``world.architecture_relations()`` and surface repeated patterns.

    Groups relations by ``(rel_kind, source_kind, target_kind)`` and
    returns a candidate for every group whose count is ``>= min_support``.

    Relations whose source or target element carries no ``kind`` are
    silently skipped and do not contribute to any pattern.

    The world is never mutated.  Results are sorted by ``candidate_id``.

    Parameters
    ----------
    world
        Open ``ArchitectureWorld`` to scan.
    min_support
        Minimum occurrence count for a pattern to become a candidate.
        Defaults to 3.

    Returns
    -------
    list[ArchitectureRuleCandidate]
        Candidates sorted by ``candidate_id``, each with a pre-filled
        DRAFT rule ready for operator review.
    """
    # Build element-kind lookup once
    element_kinds: dict[str, str] = {}
    for obj in world.find_objects("architecture_element"):
        kind = obj.get("data", {}).get("kind")
        if kind:
            element_kinds[obj["id"]] = kind

    # Group relations by (rel_kind, source_kind, target_kind)
    groups: dict[tuple[str, str, str], list[str]] = {}

    for rel in world.architecture_relations():
        src_kind = element_kinds.get(rel["source"])
        tgt_kind = element_kinds.get(rel["target"])
        if src_kind is None or tgt_kind is None:
            # Skip relations with unknown-endpoint kinds
            continue

        key = (rel["kind"], src_kind, tgt_kind)
        groups.setdefault(key, []).append(rel["id"])

    # Build candidates for groups meeting the threshold
    candidates: list[ArchitectureRuleCandidate] = []
    for (rel_kind, src_kind, tgt_kind), rel_ids in groups.items():
        support = len(rel_ids)
        if support < min_support:
            continue

        sorted_ids = sorted(rel_ids)
        example_ids = sorted_ids[:5]

        # Collect distinct run IDs (cheap: only scan runs if db exists)
        observed_runs: list[str] = []
        if world.db_path.exists():
            observed_runs = sorted(set(world.list_runs()))

        candidate_id = _candidate_id(rel_kind, src_kind, tgt_kind)

        proposed = ProposedRule(
            name=f"{candidate_id}-rule",
            statement=(
                "DRAFT from observed pattern — requires human/policy approval. "
                f"Pattern: {src_kind} -[{rel_kind}]-> {tgt_kind} "
                f"(observed {support} times)"
            ),
            forbidden_relation=rel_kind,
            source_category=src_kind,
            target_category=tgt_kind,
            severity="medium",
        )

        candidates.append(
            ArchitectureRuleCandidate(
                candidate_id=candidate_id,
                rel_kind=rel_kind,
                source_kind=src_kind,
                target_kind=tgt_kind,
                support=support,
                example_relation_ids=example_ids,
                observed_in_runs=observed_runs,
                status="candidate",
                proposed_rule=proposed,
            )
        )

    candidates.sort(key=lambda c: c.candidate_id)
    return candidates
