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
from archskillkit.packs.arch_core import (
    ClaimData,
    EvidenceData,
    ObservationData,
)
from archskillkit.ports import ArchitectureWorldPort
from archskillkit.sensors import PREDICATE_CARDINALITY  # noqa: F401 re-export
from archskillkit.sensors import (
    cardinality_for_predicate as predicate_cardinality,
)
from archskillkit.world import PromotionError

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

def ingest_scan(world: ArchitectureWorldPort, index: CodeIndex,
                scan_run_id: str) -> PromotionReport:
    """Turn every evidence edge of a scan run into an Observation backed
    by Evidence. Idempotent: the (subject, predicate, object) triple and
    the evidence provenance tuple are deduplication keys."""
    report = PromotionReport()
    for edge in index.edges_of_run(scan_run_id):
        subject = f"{edge['source_path']}::{edge['source_name']}"
        predicate = edge["kind"].lower()
        object_ref = f"{edge['target_kind']}:{edge['target_name']}"
        evidence_id = _evidence_id(
            tool="code-index", rule=edge["rule"], file=edge["source_path"],
            match_start=edge.get("match_start"),
            match_end=edge.get("match_end"))

        evidence = world.find_objects("evidence", evidence_id=evidence_id)
        if not evidence:
            ev_id = world.record_evidence(EvidenceData(
                evidence_id=evidence_id,
                tool="code-index", rule=edge["rule"],
                file=edge["source_path"],
                start_line=edge.get("match_start"),
                end_line=edge.get("match_end")))
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
                    "start_line": edge.get("match_start"),
                    "end_line": edge.get("match_end"),
                    "commit": "",
                }))
            report.observations += 1
    return report


# ---- M2-C2: claims ---------------------------------------------------

def propose_claims(world: ArchitectureWorldPort) -> int:
    """One proposed claim per observation not yet claimed; the claim is
    linked to its observation via derived_from and carries the
    observation's evidence references."""
    proposed = 0
    for obs in world.find_objects("observation"):
        if world.observation_is_claimed(obs["id"]):
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
        world.propose_derived_claim(ClaimData(
            schema_version=1,
            origin=data["origin"],
            confidence=data["confidence"],
            statement=f"{data['subject']} {data['predicate']} {data['object']}",
            subjects=[obs["id"]],
            relations=[],
            evidence_refs=[ev_id],
            contradiction_refs=[],
            status="proposed",
        ), obs["id"])
        proposed += 1
    return proposed


# Predicate cardinality lives in archskillkit.sensors (SensorContract):
# registered contracts override static defaults; re-exported above for
# backward compatibility.


def detect_generation_drift(world: ArchitectureWorldPort,
                            index: CodeIndex) -> dict:
    """Real architecture drift (docs/v2/46 F7): the semantic edge delta
    between the previous and current scan generation is mapped through the
    architecture relation vocabulary; every NEW code dependency that maps
    becomes a persisted finding — no full-world rescan involved."""
    diff = index.diff_previous_generation()
    findings: list[dict] = []
    for kind, source, target, rule in diff["added"]:
        relation = PREDICATE_TO_RELATION.get(kind.lower())
        if relation is None:
            continue
        findings.append({
            "kind": "generation_drift", "severity": "high",
            "target_id": f"{source}|{kind}|{target}",
            "detail": (f"new {kind.lower()} dependency: {source} -> {target} "
                       f"(rule: {rule})"),
        })
    persisted = world.persist_findings(findings)
    return {"generation": diff["previous_generation"],
            "findings": findings, "persisted": persisted}


def _evidence_id(*, tool: str, rule: str, file: str,
                 match_start: int | None, match_end: int | None,
                 commit: str = "") -> str:
    """Content-addressed evidence identity (docs/v2/45 §2.4): provenance
    fields hashed, never guessed from neighbouring lines."""
    import hashlib

    raw = "|".join(str(part) for part in (
        commit, file, match_start, match_end, tool, rule))
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def evaluate_claims(world: ArchitectureWorldPort) -> dict[str, int]:
    """Deterministic claim evaluation (behavior: claim_evaluator).

    1. Link contradictions: two observations sharing subject+predicate
       with different objects contradict every claim derived from them —
       only when the predicate's cardinality is `one`. `many` predicates
       legitimately hold several objects at once.
    2. Transition: contradiction → `contradicted`; otherwise DETECTED /
       high claims with resolvable evidence auto-accept; the rest stay
       `proposed` for explicit review.
    """
    counts = {"accepted": 0, "contradicted": 0, "stayed": 0}

    for claim in world.find_objects("claim", status="proposed"):
        derived = world.claim_observation_ids(claim["id"])
        for obs_id in derived:
            obs = world.get_object(obs_id)["data"]
            if predicate_cardinality(obs["predicate"]) != "one":
                continue
            for other in world.find_objects(
                "observation", subject=obs["subject"],
                predicate=obs["predicate"],
            ):
                if other["id"] == obs_id or \
                    other["data"]["object"] == obs["object"]:
                    continue
                world.link_contradicts(
                    other["id"], claim["id"],
                    "single-valued predicate holds two objects")

    for claim in world.find_objects("claim", status="proposed"):
        contradicted = bool(claim["data"].get("contradiction_refs")) or \
            world.claim_is_contradicted(claim["id"])
        if contradicted:
            world.set_claim_status(claim["id"], "contradicted")
            counts["contradicted"] += 1
            continue
        resolvable = all(
            _is_evidence(world, ref) for ref in claim["data"]["evidence_refs"])
        if claim["data"]["origin"] == "DETECTED" and \
            claim["data"]["confidence"] == "high" and resolvable:
            world.set_claim_status(claim["id"], "accepted")
            counts["accepted"] += 1
        else:
            counts["stayed"] += 1
    return counts


def _is_evidence(world: ArchitectureWorldPort, ref: str) -> bool:
    try:
        return world.get_object(ref)["type"] == "evidence"
    except (KeyError, PromotionError):
        return False


# ---- M2-C3: architecture mapper --------------------------------------

def realize_architecture(world: ArchitectureWorldPort) -> PromotionReport:
    """Map accepted claims' observations into architecture elements and
    typed relations carrying their evidence (behavior:
    architecture_mapper). Idempotent on both."""
    report = PromotionReport()
    elements_before = len(world.find_objects("architecture_element"))
    relations_before = len(world.architecture_relations())
    for claim in world.find_objects("claim", status="accepted"):
        for obs_id in world.claim_observation_ids(claim["id"]):
            obs = world.get_object(obs_id)["data"]
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


def _evidence_ids_for(world: ArchitectureWorldPort, obs: dict) -> list[str]:
    ev = world.find_objects(
        "evidence", rule=obs["evidence"].get("rule", ""),
        file=obs["evidence"].get("file", ""),
        start_line=obs["evidence"].get("start_line"))
    return [e["id"] for e in ev]


# ---- M2-C4: reviewer --------------------------------------------------

def review(world: ArchitectureWorldPort) -> dict:
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

    persisted = world.persist_findings(findings)
    return {"findings": findings, "persisted": persisted}


# ---- full pipeline -----------------------------------------------------

def discover(world: ArchitectureWorldPort, index: CodeIndex,
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
