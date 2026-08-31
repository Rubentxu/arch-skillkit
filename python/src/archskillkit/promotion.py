"""Phase C — Evidence → Architecture (docs/v2/16, M2-C1..C4).

Deterministic promotion pipeline from the Code Index (Graph A) into the
Architecture World (Graph B), following docs/v2/03's promotion rule and
docs/v2/07's reactive behaviors as plain services:

- ingest_scan            (behavior: ingest_scan)          — M2-C1
- propose_claims         (claims trazables, H2-3)          — M2-C2
- evaluate_claims        (behavior: claim_evaluator)       — M2-C2
- realize_architecture   (behavior: architecture_mapper)   — M2-C3
- review                 (behavior: reviewer)              — M2-C4
- discover               — the whole vertical slice in one call

Promotion policy (deterministic, evidence-first per docs/v2/08):
DETECTED/high claims backed by resolvable evidence are promoted
automatically; INFERRED claims require explicit acceptance; claims with
unresolved contradictions are never promoted (UAT2-006).
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field

from archskillkit.codeindex import CodeIndex
from archskillkit.packs.arch_core import EvidenceData, ObservationData
from archskillkit.world import ArchitectureWorld, PromotionError

# Code Index pseudo-kind → architecture element category (docs/v2/04).
PSEUDO_TO_CATEGORY = {
    "endpoint": "external_system",
    "topic": "topic",
    "datastore": "datastore",
    "http_client": "external_system",
}

# Observation predicate → architecture relation kind (docs/v2/04).
PREDICATE_TO_RELATION = {
    "exposes": "exposes",
    "consumes": "consumes",
    "uses": "depends_on",
    "calls": "depends_on",
    "reads": "reads",
    "writes": "writes",
    "publishes": "publishes",
}


def _utcnow() -> str:
    return _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class PromotionReport:
    observations: int = 0
    evidence: int = 0
    claims_proposed: int = 0
    claims_accepted: int = 0
    claims_contradicted: int = 0
    elements: int = 0
    relations: int = 0
    findings: int = 0
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "observations": self.observations,
            "evidence": self.evidence,
            "claims_proposed": self.claims_proposed,
            "claims_accepted": self.claims_accepted,
            "claims_contradicted": self.claims_contradicted,
            "elements": self.elements,
            "relations": self.relations,
            "findings": self.findings,
        }


# ---- M2-C1: scan edges → observations + evidence --------------------

def ingest_scan(world: ArchitectureWorld, index: CodeIndex,
                scan_run_id: str) -> PromotionReport:
    """Turn every evidence edge of a scan run into an Observation backed
    by Evidence. Idempotent: the (subject, predicate, object) triple and
    the evidence provenance tuple are deduplication keys."""
    report = PromotionReport()
    for edge in index.edges_of_run(scan_run_id):
        subject = f"{edge['source_path']}::{edge['source_name']}"
        predicate = edge["kind"].lower()
        object_ref = f"{edge['target_kind']}:{edge['target_name']}"

        evidence = world.find_objects(
            "evidence", rule=edge["rule"],
            file=edge["source_path"],
            start_line=edge["source_start_line"])
        if not evidence:
            ev_id = world.record_evidence(EvidenceData(
                tool="code-index", rule=edge["rule"],
                file=edge["source_path"],
                start_line=edge["source_start_line"]))
            report.evidence += 1
        else:
            ev_id = evidence[0]["id"]
        ev_data = world.get_object(ev_id)["data"]

        if not world.find_objects("observation", subject=subject,
                                  predicate=predicate, object=object_ref):
            world.record_observation(ObservationData(
                subject=subject, predicate=predicate, object=object_ref,
                origin="DETECTED", confidence="high",
                evidence={
                    "tool": ev_data.get("tool", "code-index"),
                    "rule": edge["rule"],
                    "file": edge["source_path"],
                    "start_line": edge["source_start_line"],
                    "end_line": None,
                    "commit": "",
                }))
            report.observations += 1
    return report


# ---- M2-C2: claims ---------------------------------------------------

def propose_claims(world: ArchitectureWorld) -> int:
    """One proposed claim per observation not yet claimed; the claim is
    linked to its observation via derived_from and carries the
    observation's evidence references."""
    proposed = 0
    for obs in world.find_objects("observation"):
        existing = world.graph.relations(target=obs["id"], type="derived_from")
        if any(world.get_object(r.source)["type"] == "claim" for r in existing):
            continue
        data = obs["data"]
        embedded = data["evidence"]
        ev = world.find_objects(
            "evidence", rule=embedded.get("rule", ""),
            file=embedded.get("file", ""),
            start_line=embedded.get("start_line"))
        if ev:
            ev_id = ev[0]["id"]
        else:
            # Directly recorded observations carry evidence inline; make
            # the evidence object real so the claim stays traceable.
            ev_id = world.record_evidence(EvidenceData(
                tool=embedded.get("tool", ""),
                rule=embedded.get("rule", ""),
                file=embedded.get("file", ""),
                start_line=embedded.get("start_line"),
                end_line=embedded.get("end_line"),
                commit=embedded.get("commit", "")))
        claim_id = world.graph.add_object("claim", {
            "schema_version": 1,
            "origin": data["origin"],
            "confidence": data["confidence"],
            "statement": f"{data['subject']} {data['predicate']} {data['object']}",
            "subjects": [obs["id"]],
            "relations": [],
            "evidence_refs": [ev_id],
            "contradiction_refs": [],
            "status": "proposed",
        }).id
        world.graph.add_relation(claim_id, obs["id"], "derived_from", {})
        proposed += 1
    return proposed


def evaluate_claims(world: ArchitectureWorld) -> dict[str, int]:
    """Deterministic claim evaluation (behavior: claim_evaluator).

    1. Link contradictions: two observations sharing subject+predicate
       with different objects contradict every claim derived from them.
    2. Transition: contradiction → `contradicted`; otherwise DETECTED /
       high claims with resolvable evidence auto-accept; the rest stay
       `proposed` for explicit review.
    """
    counts = {"accepted": 0, "contradicted": 0, "stayed": 0}

    for claim in world.find_objects("claim", status="proposed"):
        derived = [r.target for r in
                   world.graph.relations(source=claim["id"], type="derived_from")]
        for obs_id in derived:
            obs = world.get_object(obs_id)["data"]
            for other in world.find_objects(
                "observation", subject=obs["subject"],
                predicate=obs["predicate"],
            ):
                if other["id"] == obs_id or \
                    other["data"]["object"] == obs["object"]:
                    continue
                world.graph.add_relation(
                    other["id"], claim["id"], "contradicts",
                    {"reason": "same subject+predicate, different object"})

    for claim in world.find_objects("claim", status="proposed"):
        contradicted = bool(claim["data"].get("contradiction_refs")) or \
            any(r.type == "contradicts"
                for r in world.graph.relations(target=claim["id"]))
        if contradicted:
            world.graph.patch_object(claim["id"], {"status": "contradicted"})
            counts["contradicted"] += 1
            continue
        resolvable = all(
            _is_evidence(world, ref) for ref in claim["data"]["evidence_refs"])
        if claim["data"]["origin"] == "DETECTED" and \
            claim["data"]["confidence"] == "high" and resolvable:
            world.graph.patch_object(claim["id"], {"status": "accepted"})
            counts["accepted"] += 1
        else:
            counts["stayed"] += 1
    return counts


def _is_evidence(world: ArchitectureWorld, ref: str) -> bool:
    try:
        return world.get_object(ref)["type"] == "evidence"
    except (KeyError, PromotionError):
        return False


# ---- M2-C3: architecture mapper --------------------------------------

def realize_architecture(world: ArchitectureWorld) -> PromotionReport:
    """Map accepted claims' observations into architecture elements and
    typed relations carrying their evidence (behavior:
    architecture_mapper). Idempotent on both."""
    report = PromotionReport()
    elements_before = len(world.find_objects("architecture_element"))
    relations_before = len(world.architecture_relations())
    for claim in world.find_objects("claim", status="accepted"):
        for rel in world.graph.relations(source=claim["id"],
                                         type="derived_from"):
            obs = world.get_object(rel.target)["data"]
            rel_kind = PREDICATE_TO_RELATION.get(obs["predicate"])
            if rel_kind is None:
                report.warnings.append(
                    f"no architecture relation for predicate "
                    f"'{obs['predicate']}'")
                continue
            pseudo_kind, _, display = obs["object"].partition(":")
            category = PSEUDO_TO_CATEGORY.get(pseudo_kind, "component")
            src_id = world.add_architecture_element(
                obs["subject"], "component",
                obs["origin"], obs["confidence"])
            dst_id = world.add_architecture_element(display, category)
            world.add_architecture_relation(rel_kind, src_id, dst_id, {
                "origin": obs["origin"],
                "confidence": obs["confidence"],
                "rule": obs["evidence"].get("rule", ""),
                "evidence_ids": _evidence_ids_for(world, obs),
            })
    report.elements = (len(world.find_objects("architecture_element"))
                       - elements_before)
    report.relations = (len(world.architecture_relations())
                        - relations_before)
    return report


def _evidence_ids_for(world: ArchitectureWorld, obs: dict) -> list[str]:
    ev = world.find_objects(
        "evidence", rule=obs["evidence"].get("rule", ""),
        file=obs["evidence"].get("file", ""),
        start_line=obs["evidence"].get("start_line"))
    return [e["id"] for e in ev]


# ---- M2-C4: reviewer --------------------------------------------------

def review(world: ArchitectureWorld) -> dict:
    """Deterministic reviewer (behavior: reviewer): unsupported claims,
    unresolved contradictions, and automatic high relations without
    evidence (UAT2-005). Findings are persisted as `finding` objects."""
    findings: list[dict] = []

    for claim in world.find_objects("claim"):
        status = claim["data"]["status"]
        if status == "proposed" and not claim["data"].get("evidence_refs"):
            findings.append({
                "kind": "unsupported_claim", "severity": "medium",
                "target_id": claim["id"],
                "detail": claim["data"]["statement"],
            })
        elif status == "contradicted":
            findings.append({
                "kind": "contradiction", "severity": "high",
                "target_id": claim["id"],
                "detail": claim["data"]["statement"],
            })

    for rel in world.architecture_relations():
        data = rel["data"] or {}
        if data.get("confidence") == "high" and not data.get("evidence_ids"):
            findings.append({
                "kind": "missing_evidence", "severity": "high",
                "target_id": rel["id"],
                "detail": f"{rel['kind']} relation without evidence",
            })

    persisted = 0
    review_id = world.graph.add_object("review", {
        "reviewed_at": _utcnow(),
        "summary": ", ".join(sorted({f["kind"] for f in findings})) or "clean",
        "findings_count": len(findings),
    }).id
    for f in findings:
        existing = world.find_objects("finding", kind=f["kind"],
                                      target_id=f["target_id"])
        if existing:
            continue
        finding_id = world.graph.add_object("finding", {
            "kind": f["kind"], "severity": f["severity"],
            "target_id": f["target_id"], "detail": f["detail"],
        }).id
        world.graph.add_relation(finding_id, review_id, "derived_from", {})
        persisted += 1

    return {"findings": findings, "persisted": persisted}


# ---- full pipeline -----------------------------------------------------

def discover(world: ArchitectureWorld, index: CodeIndex,
             scan_run_id: str) -> PromotionReport:
    """The vertical slice of docs/v2/23:

    scan edges → observations → claims → architecture → review
    """
    report = ingest_scan(world, index, scan_run_id)
    report.claims_proposed = propose_claims(world)
    transitions = evaluate_claims(world)
    report.claims_accepted = transitions["accepted"]
    report.claims_contradicted = transitions["contradicted"]

    realized = realize_architecture(world)
    report.elements = realized.elements
    report.relations = realized.relations

    report.findings = len(review(world)["findings"])
    return report
