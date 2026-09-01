"""V2 Phase C — Evidence → Architecture (M2-C1..C4).

Observation ingestion from the Code Index (C1), claim lifecycle with
deterministic promotion policy (C2), architecture mapping (C3) and the
deterministic reviewer (C4). The vertical slice of
docs/v2/23-implementation-sequence.md lives here:

    Semgrep endpoint → Observation → Claim → ArchitectureElement

Invariants under test: UAT2-005 (automatic high relations carry
evidence), UAT2-006 (contradictions are never silently promoted) and
H2-1 (the world still replays after every mutation).
"""

import json

import pytest

from archskillkit.codeindex import CodeIndex
from conftest import KOTLIN_RUN, load_fixture
from archskillkit.packs.arch_core import ClaimData, EvidenceData, ObservationData
from archskillkit.promotion import (
    PromotionError,
    discover,
    evaluate_claims,
    ingest_scan,
    propose_claims,
    realize_architecture,
    review,
)

HTTP_KT = "kotlin-spring/src/main/kotlin/demo/infra/Http.kt"


def inferred_observation(subject="svc.billing", predicate="exposes",
                         obj="POST /internal"):
    return ObservationData(
        subject=subject, predicate=predicate, object=obj,
        origin="INFERRED", confidence="medium",
        evidence=EvidenceData(tool="agent", rule="manual", file="notes.md"),
    )


class TestIngestScan:
    def test_observations_and_evidence_created(self, kotlin_world_index):
        world, index = kotlin_world_index
        report = ingest_scan(world, index, scan_run_id=KOTLIN_RUN)
        assert report.observations == 5
        assert report.evidence == 5

    def test_observation_triple_carries_provenance(self, kotlin_world_index):
        world, index = kotlin_world_index
        ingest_scan(world, index, scan_run_id=KOTLIN_RUN)
        obs = world.find_objects("observation", subject=f"{HTTP_KT}::getPayment")
        assert len(obs) == 1
        data = obs[0]["data"]
        assert data["predicate"] == "exposes"
        assert data["object"] == "endpoint:endpoint@11"
        assert data["evidence"]["rule"] == "spring.endpoint"
        assert data["evidence"]["file"].endswith("Http.kt")

    def test_rerun_is_idempotent(self, kotlin_world_index):
        world, index = kotlin_world_index
        first = ingest_scan(world, index, scan_run_id=KOTLIN_RUN)
        second = ingest_scan(world, index, scan_run_id=KOTLIN_RUN)
        assert second.observations == 0
        assert second.evidence == 0
        snap = world.snapshot()
        assert snap["counts"]["observation"] == first.observations


class TestClaimProposal:
    def test_one_claim_per_observation(self, kotlin_world_index):
        world, index = kotlin_world_index
        ingest_scan(world, index, scan_run_id=KOTLIN_RUN)
        proposed = propose_claims(world)
        assert proposed == 5
        claims = world.find_objects("claim")
        assert all(c["data"]["status"] == "proposed" for c in claims)
        assert all(c["data"]["evidence_refs"] for c in claims)

    def test_proposal_is_idempotent(self, kotlin_world_index):
        world, index = kotlin_world_index
        ingest_scan(world, index, scan_run_id=KOTLIN_RUN)
        assert propose_claims(world) == 5
        assert propose_claims(world) == 0
        assert len(world.find_objects("claim")) == 5


class TestClaimLifecycle:
    def test_detected_high_claims_auto_accept(self, kotlin_world_index):
        world, index = kotlin_world_index
        ingest_scan(world, index, scan_run_id=KOTLIN_RUN)
        propose_claims(world)
        counts = evaluate_claims(world)
        assert counts["accepted"] == 5
        statuses = {c["data"]["status"] for c in world.find_objects("claim")}
        assert statuses == {"accepted"}

    def test_inferred_claims_require_explicit_accept(self, kotlin_world_index):
        world, index = kotlin_world_index
        world.record_observation(inferred_observation())
        assert propose_claims(world) == 1
        counts = evaluate_claims(world)
        assert counts["accepted"] == 0
        proposal = next(c for c in world.find_objects("claim")
                        if c["data"]["origin"] == "INFERRED")
        assert proposal["data"]["status"] == "proposed"
        world.accept_claim(proposal["id"], actor="reviewer")
        assert world.get_object(proposal["id"])["data"]["status"] == "accepted"

    def test_accept_requires_evidence(self, kotlin_world_index):
        world, _ = kotlin_world_index
        claim_id = world.propose_claim(ClaimData(
            statement="ghost exists", subjects=["ghost"]))
        with pytest.raises(PromotionError):
            world.accept_claim(claim_id)

    def test_contradictions_block_silent_promotion(self, kotlin_world_index):
        # UAT2-006 refined (V2.3-F1): contradiction requires a single-valued
        # predicate. `belongs_to` is ONE: two distinct objects contradict.
        world, _ = kotlin_world_index
        world.record_observation(inferred_observation(
            subject="svc.payments", predicate="belongs_to", obj="domain.payments"))
        world.record_observation(inferred_observation(
            subject="svc.payments", predicate="belongs_to", obj="domain.billing"))
        propose_claims(world)
        counts = evaluate_claims(world)
        assert counts["contradicted"] == 2
        assert counts["accepted"] == 0
        statuses = {c["data"]["status"] for c in world.find_objects("claim")}
        assert statuses == {"contradicted"}
        with pytest.raises(PromotionError):
            world.accept_claim(world.find_objects("claim")[0]["id"])

    def test_many_valued_predicates_never_contradict(self, kotlin_world_index):
        # PR-5 / V2.3-F1: a `many` predicate legitimately holds several
        # objects — `uses postgres` + `uses mongodb` are two facts, not a
        # contradiction (the old behavior wrongly flagged this).
        world, _ = kotlin_world_index
        world.record_observation(inferred_observation(
            subject="svc.payments", predicate="uses", obj="postgres"))
        world.record_observation(inferred_observation(
            subject="svc.payments", predicate="uses", obj="mongodb"))
        propose_claims(world)
        counts = evaluate_claims(world)
        assert counts["contradicted"] == 0
        assert counts["stayed"] == 2
        statuses = {c["data"]["status"] for c in world.find_objects("claim")}
        assert statuses == {"proposed"}


class TestArchitectureMapper:
    @pytest.fixture()
    def promoted(self, kotlin_world_index):
        world, index = kotlin_world_index
        discover(world, index, scan_run_id=KOTLIN_RUN)
        return world

    def test_elements_created_with_categories(self, promoted):
        elements = promoted.find_objects("architecture_element")
        kinds = {}
        for el in elements:
            kinds.setdefault(el["data"]["kind"], set()).add(el["data"]["name"])
        assert len(kinds.get("component", set())) == 5  # 5 handlers/repositories
        assert len(kinds.get("external_system", set())) == 3  # endpoints
        assert len(kinds.get("topic", set())) == 1
        assert len(kinds.get("datastore", set())) == 1

    def test_relations_typed_and_evidenced(self, promoted):
        relations = promoted.architecture_relations()
        by_kind = {}
        for rel in relations:
            by_kind.setdefault(rel["kind"], []).append(rel)
        assert len(by_kind.get("exposes", [])) == 3
        assert len(by_kind.get("consumes", [])) == 1
        assert len(by_kind.get("depends_on", [])) == 1
        # UAT2-005 invariant: automatic high relations link evidence
        for rel in relations:
            assert rel["data"]["evidence_ids"], rel

    def test_mapping_is_idempotent(self, promoted):
        before = promoted.snapshot()["counts"]
        assert realize_architecture(promoted).elements == 0
        assert promoted.snapshot()["counts"] == before

    def test_contradicted_claims_never_reach_architecture(self, kotlin_world_index):
        world, index = kotlin_world_index
        world.record_observation(inferred_observation(
            subject="svc.payments", predicate="uses", obj="postgres"))
        world.record_observation(inferred_observation(
            subject="svc.payments", predicate="uses", obj="mongodb"))
        discover(world, index, scan_run_id=KOTLIN_RUN)
        names = {el["data"]["name"] for el in
                 world.find_objects("architecture_element")}
        assert "svc.payments" not in names
        assert "postgres" not in names and "mongodb" not in names


class TestReviewer:
    def test_clean_pipeline_has_no_findings(self, kotlin_world_index):
        world, index = kotlin_world_index
        report = review(world)  # nothing ingested yet: empty review
        assert report["findings"] == []

    def test_unsupported_claim_detected(self, kotlin_world_index):
        world, _ = kotlin_world_index
        world.propose_claim(ClaimData(
            statement="unsupported guess", subjects=["ghost-module"]))
        report = review(world)
        kinds = [f["kind"] for f in report["findings"]]
        assert kinds == ["unsupported_claim"]

    def test_missing_evidence_invariant_enforced(self, kotlin_world_index):
        world, index = kotlin_world_index
        discover(world, index, scan_run_id=KOTLIN_RUN)
        # forge an unevidenced architecture relation directly
        els = world.find_objects("architecture_element")
        a = next(e for e in els if e["data"]["kind"] == "component")
        b = next(e for e in els if e["data"]["kind"] == "datastore")
        world.add_architecture_relation("depends_on", a["id"], b["id"], data={
            "origin": "DETECTED", "confidence": "high", "rule": "forged",
            "evidence_ids": [],
        })
        report = review(world)
        assert any(f["kind"] == "missing_evidence" for f in report["findings"])
        assert report["persisted"] == len(report["findings"])

    def test_findings_are_replayable(self, kotlin_world_index):
        world, index = kotlin_world_index
        world.propose_claim(ClaimData(statement="guess", subjects=["g"]))
        review(world)
        assert world.replay_verify().ok


class TestVerticalSlice:
    def test_full_pipeline_report(self, kotlin_world_index):
        world, index = kotlin_world_index
        report = discover(world, index, scan_run_id=KOTLIN_RUN)
        assert report.as_dict() == {
            "observations": 5, "evidence": 5, "claims_proposed": 5,
            "claims_accepted": 5, "claims_contradicted": 0,
            "elements": 10, "relations": 5, "findings": 0,
        }

    def test_world_replays_after_full_pipeline(self, kotlin_world_index):
        world, index = kotlin_world_index
        discover(world, index, scan_run_id=KOTLIN_RUN)
        report = world.replay_verify()
        assert report.ok, report.detail

    def test_second_discover_run_changes_nothing(self, kotlin_world_index):
        world, index = kotlin_world_index
        discover(world, index, scan_run_id=KOTLIN_RUN)
        # reviews are an append-only audit trail; everything else is stable
        before = {k: v for k, v in world.snapshot()["counts"].items()
                  if k != "review"}
        discover(world, index, scan_run_id=KOTLIN_RUN)
        after = {k: v for k, v in world.snapshot()["counts"].items()
                 if k != "review"}
        assert after == before
