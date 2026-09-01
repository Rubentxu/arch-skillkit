"""Domain repositories and policy services (docs/v2/46 F6).

Aggregate-focused boundaries behind the `ArchitectureWorld` facade: the
facade delegates; ActiveGraph calls live here and in world.py's core.
Each repository/service receives the world (an
`ArchitectureWorldPort`-shaped object) and never imports ActiveGraph.
"""

from __future__ import annotations

import datetime as _dt

from archskillkit.errors import PromotionError


def utcnow() -> str:
    return _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds")


class ClaimRepository:
    """Claims: derivation, contradiction gating and status transitions."""

    def __init__(self, world):
        self.world = world

    def add(self, claim) -> str:
        return self.world.graph.add_object("claim", claim.model_dump()).id

    def link_evidenced_by(self, claim_id: str, evidence_id: str) -> str:
        return self.world.graph.add_relation(
            claim_id, evidence_id, "evidenced_by", {}).id

    def observation_is_claimed(self, observation_id: str) -> bool:
        existing = self.world.graph.relations(target=observation_id,
                                              type="derived_from")
        return any(self.world.get_object(r.source)["type"] == "claim"
                   for r in existing)

    def propose_derived_claim(self, claim, observation_id: str) -> str:
        claim_id = self.add(claim)
        self.world.graph.add_relation(claim_id, observation_id,
                                      "derived_from", {})
        return claim_id

    def observation_ids_of_claim(self, claim_id: str) -> list[str]:
        return [r.target for r in
                self.world.graph.relations(source=claim_id,
                                           type="derived_from")]

    def link_contradicts(self, observation_id: str, claim_id: str,
                         reason: str) -> None:
        self.world.graph.add_relation(observation_id, claim_id,
                                      "contradicts", {"reason": reason})

    def is_contradicted(self, claim_id: str) -> bool:
        return any(r.type == "contradicts"
                   for r in self.world.graph.relations(target=claim_id))

    def set_status(self, claim_id: str, status: str) -> None:
        self.world.graph.patch_object(claim_id, {"status": status})

    def accept(self, claim_id: str, actor: str = "user") -> None:
        """Explicit acceptance (M2-C2): refused for claims without evidence
        or with unresolved contradictions — never silent."""
        claim = self.world.get_object(claim_id)
        if claim["type"] != "claim":
            raise PromotionError(f"{claim_id} is not a claim")
        status = claim["data"].get("status")
        if status == "accepted":
            return
        if status == "contradicted":
            raise PromotionError(
                f"claim {claim_id} is contradicted; resolve the conflict "
                "first")
        if not claim["data"].get("evidence_refs"):
            raise PromotionError(
                f"claim {claim_id} has no evidence references")
        self.world.graph.patch_object(claim_id, {"status": "accepted"},
                                      actor=actor)


class ArchitectureRepository:
    """Architecture elements and typed relations (idempotent by name)."""

    def __init__(self, world):
        self.world = world

    def add_element(self, name: str, kind: str, origin: str = "DETECTED",
                    confidence: str = "high") -> str:
        existing = self.world.find_objects("architecture_element", name=name)
        if existing:
            return existing[0]["id"]
        return self.world.graph.add_object("architecture_element", {
            "name": name, "kind": kind, "origin": origin,
            "confidence": confidence, "summary": "",
        }).id

    def add_relation(self, kind: str, source_id: str, target_id: str,
                     data: dict | None = None) -> str:
        for rel in self.world.graph.relations(source=source_id,
                                              target=target_id):
            if rel.type == kind:
                return rel.id
        return self.world.graph.add_relation(
            source_id, target_id, kind, data or {}).id

    def relations(self) -> list[dict]:
        """Typed edges whose two endpoints are architecture elements —
        the domain-level view of ArchitectureRelation (docs/v2/04)."""
        elements = {o["id"]
                    for o in self.world.find_objects("architecture_element")}
        return [
            {"id": rel.id, "kind": rel.type, "source": rel.source,
             "target": rel.target, "data": rel.data}
            for rel in self.world.graph.relations()
            if rel.source in elements and rel.target in elements
        ]

    def remove_relation(self, relation_id: str) -> None:
        self.world.graph.remove_relation(relation_id)

    def remove_element(self, element_id: str) -> None:
        self.world.graph.remove_object(element_id)


class ArchitecturePolicyService:
    """Boundary rules, drift and findings persistence (Phase F, ADR-0022)."""

    def __init__(self, world):
        self.world = world

    def record_rule(self, name: str, statement: str,
                    forbidden_relation: str, source_category: str,
                    target_category: str, severity: str = "high") -> str:
        """Declare a structured boundary rule (ADR-0022): the
        `source_category -[forbidden_relation]-> target_category` pattern
        is drift. Idempotent by rule name."""
        existing = self.world.find_objects("architecture_rule", name=name)
        if existing:
            return existing[0]["id"]
        return self.world.graph.add_object("architecture_rule", {
            "name": name, "statement": statement,
            "forbidden_relation": forbidden_relation,
            "source_category": source_category,
            "target_category": target_category,
            "severity": severity,
        }).id

    def persist_findings(self, findings: list[dict]) -> int:
        """Persist findings as objects linked to a fresh review audit
        object. Dedup key: (kind, target_id). Returns new findings count."""
        review_id = self.world.graph.add_object("review", {
            "reviewed_at": utcnow(),
            "summary": ", ".join(sorted({f["kind"] for f in findings}))
                       or "clean",
            "findings_count": len(findings),
        }).id
        persisted = 0
        for finding in findings:
            existing = self.world.find_objects("finding",
                                               kind=finding["kind"],
                                               target_id=finding["target_id"])
            if existing:
                continue
            finding_id = self.world.graph.add_object("finding", {
                "kind": finding["kind"],
                "severity": finding.get("severity", "medium"),
                "target_id": finding.get("target_id", ""),
                "detail": finding.get("detail", ""),
            }).id
            self.world.graph.add_relation(finding_id, review_id,
                                          "derived_from", {})
            persisted += 1
        return persisted

    def detect_drift(self) -> dict:
        """Architecture drift (M2-F1): architecture relations matching a
        declared boundary rule become findings — no LLM involved."""
        rules = self.world.find_objects("architecture_rule")
        findings: list[dict] = []
        if rules:
            elements = {o["id"]: o["data"] for o in
                        self.world.find_objects("architecture_element")}
            for rule in rules:
                data = rule["data"]
                for rel in self.world.architecture_relations():
                    src = elements.get(rel["source"], {})
                    dst = elements.get(rel["target"], {})
                    if (rel["kind"] == data["forbidden_relation"]
                        and src.get("kind") == data["source_category"]
                            and dst.get("kind") == data["target_category"]):
                        findings.append({
                            "kind": "architecture_drift",
                            "severity": data.get("severity", "high"),
                            "target_id": rel["id"],
                            "rule": data["name"],
                            "detail": (
                                f"[{data['name']}] {data['statement']}: "
                                f"{src.get('name')} -{rel['kind']}-> "
                                f"{dst.get('name')}"),
                        })
        persisted = self.persist_findings(findings)
        return {"findings": findings, "persisted": persisted}

    def detect_stale_model(self, index) -> dict:
        """Stale model (M2-F3): evidence backing the accepted architecture
        whose (file, line) location is absent from the current Code Index."""
        locations = index.symbol_locations()
        findings: list[dict] = []
        checked: set[str] = set()
        for rel in self.world.architecture_relations():
            for ev_id in (rel["data"] or {}).get("evidence_ids", []):
                if ev_id in checked:
                    continue
                checked.add(ev_id)
                try:
                    ev = self.world.get_object(ev_id)["data"]
                except KeyError:
                    continue
                location = (ev.get("file", ""), ev.get("start_line"))
                if location not in locations:
                    findings.append({
                        "kind": "stale_evidence", "severity": "medium",
                        "target_id": ev_id,
                        "detail": (
                            f"{ev.get('file')}:{ev.get('start_line')} "
                            "is no longer reported by the current "
                            "code index"),
                    })
        persisted = self.persist_findings(findings)
        return {"findings": findings, "persisted": persisted}


class ProposalService:
    """Proposal paperwork inside a fork run (M2-G1, UAT2-014)."""

    def __init__(self, world):
        self.world = world

    def record(self, name: str, rationale: str = "") -> str:
        """Register the proposal paperwork inside the fork (M2-G1).
        Idempotent by proposal name."""
        existing = self.world.find_objects("proposal", name=name)
        if existing:
            return existing[0]["id"]
        return self.world.graph.add_object("proposal", {
            "name": name, "status": "open", "rationale": rationale,
            "fork_run": self.world.run_id, "created_at": utcnow(),
        }).id

    def get(self, name: str) -> dict:
        proposals = self.world.find_objects("proposal", name=name)
        if not proposals:
            raise PromotionError(
                f"no proposal named '{name}' in {self.world.run_id}")
        return proposals[0]

    def approve(self, name: str, actor: str) -> None:
        if not actor:
            raise PromotionError("approval requires a named approver")
        proposal = self.get(name)
        if proposal["data"]["status"] == "rejected":
            raise PromotionError(f"proposal '{name}' was rejected")
        self.world.graph.patch_object(proposal["id"],
                                      {"status": "approved"}, actor=actor)

    def reject(self, name: str, actor: str) -> None:
        if not actor:
            raise PromotionError("rejection requires a named actor")
        proposal = self.get(name)
        self.world.graph.patch_object(proposal["id"],
                                      {"status": "rejected"}, actor=actor)
