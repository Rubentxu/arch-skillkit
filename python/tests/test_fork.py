"""V2 Phase G — fork/diff of the architecture (M2-G1..G4, docs/v2/08).

Forks branch the Architecture World's event log at the current point
(ActiveGraph native fork); proposals mutate the fork, structural diffs
compare the architecture layers, and promotion requires explicit
approval (UAT2-014). Invariants: fork isolation (UAT2-012), diff
correctness for add/remove/change (UAT2-013), and the scenario pattern
of docs/v2/19 SPIKE-05 (sync payment → async payment).
"""

import pytest
from conftest import KOTLIN_RUN

from archskillkit.promotion import discover
from archskillkit.proposals import (
    PromotionRequired,
    promote,
    structural_diff,
)


@pytest.fixture()
def main_world(kotlin_world_index):
    world, index = kotlin_world_index
    discover(world, index, scan_run_id=KOTLIN_RUN)
    return world


def _apply_async_payments(fork):
    """SPIKE-05 scenario: introduce an async payments processor."""
    src = fork.add_architecture_element("payments.async.processor", "component",
                                        "INFERRED", "medium")
    dst = fork.add_architecture_element("payments.events", "topic")
    fork.add_architecture_relation("publishes", src, dst, {
        "origin": "INFERRED", "confidence": "medium",
        "rule": "proposal", "evidence_ids": [],
    })
    return src, dst


class TestFork:
    def test_fork_starts_from_main_architecture(self, main_world):
        fork = main_world.fork("async-payments")
        assert fork.snapshot()["counts"]["architecture_element"] == \
            main_world.snapshot()["counts"]["architecture_element"]

    def test_fork_does_not_alter_main(self, main_world):
        # UAT2-012 / H2-8
        before = main_world.snapshot()
        fork = main_world.fork("async-payments")
        _apply_async_payments(fork)
        assert main_world.snapshot() == before
        assert main_world.replay_verify().ok
        names = {o["data"]["name"]
                 for o in fork.find_objects("architecture_element")}
        assert "payments.async.processor" in names
        assert "payments.async.processor" not in {
            o["data"]["name"]
            for o in main_world.find_objects("architecture_element")}

    def test_fork_is_idempotent_by_name(self, main_world):
        first = main_world.fork("async-payments")
        _first_events_before_fork = len(list(first.snapshot()["objects"]))
        second = main_world.fork("async-payments")
        assert second.run_id == first.run_id
        assert second.snapshot()["counts"] == first.snapshot()["counts"]

    def test_distinct_names_get_distinct_forks(self, main_world):
        a = main_world.fork("scenario-a")
        b = main_world.fork("scenario-b")
        assert a.run_id != b.run_id


class TestStructuralDiff:
    def test_empty_diff_when_nothing_changed(self, main_world):
        fork = main_world.fork("no-change")
        diff = structural_diff(main_world, fork)
        assert diff.is_empty()

    def test_diff_detects_additions(self, main_world):
        # UAT2-013: added elements/relations
        fork = main_world.fork("async-payments")
        _apply_async_payments(fork)
        diff = structural_diff(main_world, fork)
        assert diff.elements_added == ["payments.async.processor",
                                       "payments.events"]
        assert len(diff.relations_added) == 1
        rel = diff.relations_added[0]
        assert rel["kind"] == "publishes"
        assert rel["source"] == "payments.async.processor"
        assert diff.elements_removed == []

    def test_diff_detects_removal_and_confidence_change(self, main_world):
        fork = main_world.fork("trim")
        victim = next(o for o in fork.find_objects("architecture_element")
                      if o["data"]["kind"] == "interface")
        fork.graph.remove_object(victim["id"])
        other = next(o for o in fork.find_objects("architecture_element")
                     if o["data"]["kind"] == "interface"
                     and o["id"] != victim["id"])
        fork.graph.patch_object(other["id"], {"confidence": "medium"})
        diff = structural_diff(main_world, fork)
        assert victim["data"]["name"] in diff.elements_removed
        changed = {c["element"]: c["to"] for c in diff.confidence_changed}
        assert changed.get(other["data"]["name"]) == "medium"

    def test_diff_reports_changed_relations_by_evidence(self, main_world):
        # docs/v2/08: "evidence changed" is a diff dimension of its own —
        # same relation triple, new rule
        fork = main_world.fork("re-evidence")
        rel = fork.architecture_relations()[0]
        fork.graph.remove_relation(rel["id"])
        fork.add_architecture_relation(rel["kind"], rel["source"], rel["target"], {
            "origin": "DETECTED", "confidence": "high",
            "rule": "rechecked", "evidence_ids": rel["data"]["evidence_ids"],
        })
        diff = structural_diff(main_world, fork)
        assert diff.relations_added == [] and diff.relations_removed == []
        assert len(diff.evidence_changed) == 1
        changed = diff.evidence_changed[0]
        assert changed["from_rule"] != "rechecked"
        assert changed["to_rule"] == "rechecked"

    def test_findings_new_and_resolved(self, main_world):
        fork = main_world.fork("findings")
        main_world.persist_findings([{
            "kind": "unsupported_claim", "severity": "medium",
            "target_id": "claim#x", "detail": "main-only finding"}])
        fork.persist_findings([{
            "kind": "contradiction", "severity": "high",
            "target_id": "claim#y", "detail": "fork-only finding"}])
        diff = structural_diff(main_world, fork)
        details_new = {f["detail"] for f in diff.findings_new}
        details_resolved = {f["detail"] for f in diff.findings_resolved}
        assert "fork-only finding" in details_new
        assert "main-only finding" in details_resolved


class TestPromotion:
    def test_promote_requires_approval(self, main_world):
        # UAT2-014: a proposal is not accepted without policy/approval
        fork = main_world.fork("async-payments")
        _apply_async_payments(fork)
        fork.record_proposal("async-payments", rationale="decouple payments")
        with pytest.raises(PromotionRequired):
            promote(main_world, fork)

    def test_promote_applies_the_diff(self, main_world):
        fork = main_world.fork("async-payments")
        _apply_async_payments(fork)
        fork.record_proposal("async-payments", rationale="decouple payments")
        fork.approve_proposal("async-payments", actor="architect")
        summary = promote(main_world, fork)
        assert summary["elements_added"] == 2
        assert summary["relations_added"] == 1
        names = {o["data"]["name"]
                 for o in main_world.find_objects("architecture_element")}
        assert {"payments.async.processor", "payments.events"} <= names
        id_to_name = {o["id"]: o["data"]["name"] for o
                      in main_world.find_objects("architecture_element")}
        rels = {(r["kind"], id_to_name[r["source"]], id_to_name[r["target"]])
                for r in main_world.architecture_relations()}
        assert ("publishes", "payments.async.processor", "payments.events") in rels
        assert main_world.replay_verify().ok

    def test_promote_without_proposal_object_refused(self, main_world):
        fork = main_world.fork("no-paperwork")
        _apply_async_payments(fork)
        with pytest.raises(PromotionRequired):
            promote(main_world, fork)

    def test_promote_is_idempotent(self, main_world):
        fork = main_world.fork("async-payments")
        _apply_async_payments(fork)
        fork.record_proposal("async-payments", rationale="decouple")
        fork.approve_proposal("async-payments", actor="architect")
        promote(main_world, fork)
        before = main_world.snapshot()["counts"]
        summary = promote(main_world, fork)
        assert summary["elements_added"] == 0
        assert main_world.snapshot()["counts"] == before

    def test_reject_keeps_the_scenario(self, main_world):
        fork = main_world.fork("async-payments")
        _apply_async_payments(fork)
        fork.record_proposal("async-payments", rationale="decouple")
        fork.reject_proposal("async-payments", actor="architect")
        proposal = fork.find_objects("proposal")[0]
        assert proposal["data"]["status"] == "rejected"
        # the scenario stays browsable, main stays untouched
        assert fork.find_objects("architecture_element")
        with pytest.raises(PromotionRequired):
            promote(main_world, fork)  # rejected proposals never promote
