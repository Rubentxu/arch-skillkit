"""V2 Phase F — reactive architecture: deterministic drift + stale model.

Drift (M2-F1) is the difference between accepted/declared architecture
and current evidence, detected WITHOUT an LLM (docs/v2/09, ADR-0022):
structured rules forbid relation kinds between element categories, and
any matching architecture relation becomes a `architecture_drift`
finding. Stale model (M2-F3) flags accepted architecture whose evidence
points at locations absent from the current Code Index.
"""

import pytest
from conftest import KOTLIN_RUN, load_fixture

from archskillkit.promotion import discover


@pytest.fixture()
def world(kotlin_world_index):
    world, index = kotlin_world_index
    discover(world, index, scan_run_id=KOTLIN_RUN)
    return world, index


class TestRules:
    def test_record_and_list_rules(self, world):
        w, _ = world
        rule_id = w.record_architecture_rule(
            name="no-endpoint-to-datastore",
            statement="external systems must not depend on datastores",
            forbidden_relation="depends_on",
            source_category="external_system",
            target_category="datastore",
        )
        assert rule_id
        rules = w.find_objects("architecture_rule")
        assert len(rules) == 1
        assert rules[0]["data"]["forbidden_relation"] == "depends_on"

    def test_rule_recording_is_idempotent(self, world):
        w, _ = world
        w.record_architecture_rule(name="r", statement="s",
                                   forbidden_relation="exposes",
                                   source_category="component",
                                   target_category="external_system")
        w.record_architecture_rule(name="r", statement="s",
                                   forbidden_relation="exposes",
                                   source_category="component",
                                   target_category="external_system")
        assert len(w.find_objects("architecture_rule")) == 1


class TestDriftDetection:
    def test_violating_relation_produces_finding(self, world):
        w, _ = world
        w.record_architecture_rule(
            name="no-endpoint-to-datastore",
            statement="external systems must not depend on datastores",
            forbidden_relation="depends_on",
            source_category="external_system",
            target_category="datastore",
        )
        # forge the violation: endpoint@11 depends_on the datastore element
        ext = next(e for e in w.find_objects("architecture_element")
                   if e["data"]["kind"] == "external_system")
        store = next(e for e in w.find_objects("architecture_element")
                     if e["data"]["kind"] == "datastore")
        w.add_architecture_relation("depends_on", ext["id"], store["id"],
                                    {"origin": "DETECTED",
                                     "confidence": "high",
                                     "rule": "forged", "evidence_ids": []})
        report = w.detect_drift()
        kinds = [f["kind"] for f in report["findings"]]
        assert "architecture_drift" in kinds
        finding = next(f for f in report["findings"]
                       if f["kind"] == "architecture_drift")
        assert finding["severity"] == "high"
        assert finding["rule"] == "no-endpoint-to-datastore"

    def test_clean_world_has_no_drift(self, world):
        w, _ = world
        w.record_architecture_rule(
            name="no-topic-endpoint",
            statement="topics must not expose interfaces",
            forbidden_relation="exposes",
            source_category="topic",
            target_category="external_system",
        )
        report = w.detect_drift()
        assert report["findings"] == []

    def test_drift_findings_are_persisted_once(self, world):
        w, _ = world
        w.record_architecture_rule(
            name="r", statement="s", forbidden_relation="depends_on",
            source_category="external_system", target_category="datastore")
        ext = next(e for e in w.find_objects("architecture_element")
                   if e["data"]["kind"] == "external_system")
        store = next(e for e in w.find_objects("architecture_element")
                     if e["data"]["kind"] == "datastore")
        w.add_architecture_relation("depends_on", ext["id"], store["id"],
                                    {"evidence_ids": []})
        first = w.detect_drift()
        second = w.detect_drift()
        assert first["findings"]
        assert second["persisted"] == 0  # dedup by (kind, rule, target)

    def test_drift_without_rules_is_clean(self, world):
        w, _ = world
        assert w.detect_drift()["findings"] == []

    def test_replay_after_drift(self, world):
        w, _ = world
        w.record_architecture_rule(
            name="r", statement="s", forbidden_relation="depends_on",
            source_category="external_system", target_category="datastore")
        ext = next(e for e in w.find_objects("architecture_element")
                   if e["data"]["kind"] == "external_system")
        store = next(e for e in w.find_objects("architecture_element")
                     if e["data"]["kind"] == "datastore")
        w.add_architecture_relation("depends_on", ext["id"], store["id"],
                                    {"evidence_ids": []})
        w.detect_drift()
        assert w.replay_verify().ok


class TestStaleModel:
    def test_evidence_outside_current_index_is_stale(self, world):
        w, index = world
        # regenerate the index EMPTY: the accepted architecture's evidence
        # now points at locations the current scan no longer reports
        index.regenerate()
        report = w.detect_stale_model(index)
        assert report["findings"]
        assert all(f["kind"] == "stale_evidence" for f in report["findings"])

    def test_fresh_index_is_not_stale(self, world):
        w, index = world
        index.regenerate()
        index.ingest_astgrep(load_fixture("astgrep-kotlin.json"),
                             scan_run_id=KOTLIN_RUN, scan_root=index.db_path.parent)
        index.ingest_semgrep(load_fixture("semgrep-kotlin.json"),
                             scan_run_id=KOTLIN_RUN, scan_root=index.db_path.parent)
        # same run re-ingested: evidence locations still exist
        report = w.detect_stale_model(index)
        assert report["findings"] == []

    def test_stale_index_never_promotes(self, world):
        # re-running discover after an empty index proposes nothing new:
        # stale evidence does not become fresh knowledge
        w, index = world
        index.regenerate()
        discover(w, index, scan_run_id=KOTLIN_RUN)
        assert w.snapshot()["counts"]["observation"] == 5
