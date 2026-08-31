"""arch-core pack: the M2-A2 domain ontology.

Schemas follow design/schemas/*.yaml; the type/relation inventory follows
design/packs/arch-core.md. Only the object types modeled so far
(project, scan_run, observation, evidence, claim) declare full schemas;
the remaining arch-core types arrive with their milestones (Phase C+).
"""

import pytest
from pydantic import ValidationError

from archskillkit.packs.arch_core import (
    ARCH_CORE_OBJECT_TYPES,
    ARCH_CORE_RELATION_TYPES,
    ClaimData,
    ObservationData,
    pack,
)


class TestPackShape:
    def test_pack_identity(self):
        assert pack.name == "arch_core"
        assert pack.version
        assert pack.object_types
        assert pack.behaviors == ()  # behaviors arrive in Phase C (claim_evaluator, ...)

    def test_unique_names(self):
        obj_names = [t.name for t in pack.object_types]
        assert len(obj_names) == len(set(obj_names))
        rel_names = [t.name for t in pack.relation_types]
        assert len(rel_names) == len(set(rel_names))

    def test_core_object_types_declared(self):
        # M2-A2 core five + M2-C4 reviewer types (finding, review)
        assert ARCH_CORE_OBJECT_TYPES == (
            "project", "scan_run", "observation", "evidence", "claim",
            "finding", "review",
        )

    def test_core_relations_declared(self):
        # design/packs/arch-core.md relation inventory
        for rel in ("supports", "contradicts", "evidenced_by",
                    "derived_from", "validates", "invalidates", "supersedes"):
            assert rel in ARCH_CORE_RELATION_TYPES

    def test_evidenced_by_endpoints(self):
        rel = next(r for r in pack.relation_types if r.name == "evidenced_by")
        assert "claim" in rel.source_types
        assert "evidence" in rel.target_types


class TestObservationSchema:
    def test_valid_minimal(self):
        obs = ObservationData(
            subject="pipeline.api", predicate="exposes",
            object="POST /orders",
            evidence={"tool": "semgrep"},
        )
        assert obs.schema_version == 1
        assert obs.origin == "DETECTED"
        assert obs.confidence == "high"
        assert obs.evidence.rule == ""

    def test_invalid_origin_rejected(self):
        with pytest.raises(ValidationError):
            ObservationData(
                subject="s", predicate="p", object="o", tool="t", origin="GUESSED",
            )

    def test_invalid_confidence_rejected(self):
        with pytest.raises(ValidationError):
            ObservationData(
                subject="s", predicate="p", object="o", tool="t", confidence="certain",
            )

    def test_tool_required(self):
        with pytest.raises(ValidationError):
            ObservationData(subject="s", predicate="p", object="o")


class TestClaimSchema:
    def test_defaults_follow_design_schema(self):
        claim = ClaimData(statement="payments is a bounded context",
                          subjects=["payments"])
        assert claim.origin == "INFERRED"
        assert claim.confidence == "medium"
        assert claim.status == "proposed"
        assert claim.evidence_refs == []
        assert claim.contradiction_refs == []

    def test_invalid_status_rejected(self):
        with pytest.raises(ValidationError):
            ClaimData(statement="x", status="installed")

    def test_subjects_required_non_empty(self):
        with pytest.raises(ValidationError):
            ClaimData(statement="x", subjects=[])
