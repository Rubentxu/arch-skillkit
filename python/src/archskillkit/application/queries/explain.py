"""Explain use case (docs/v2/55 §2): reconstruct the evidence lineage
of a subject — element, claim, observation or evidence object.

The explanation is a read model: nothing here mutates the world. Where
the model cannot provide lineage (e.g. elements carry no claim link in
V2.4 M0), the gap is declared instead of hidden.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from archskillkit.application.ports.architecture_query import (
        ArchitectureQueryPort,
    )

EXPLANATION_SCHEMA = "arch-skillkit/explanation-v1"


class SubjectNotFound(LookupError):
    """Stable error code per docs/v2/55 §10."""

    code = "SUBJECT_NOT_FOUND"


class Explanation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema: Literal["arch-skillkit/explanation-v1"] = EXPLANATION_SCHEMA  # type: ignore[assignment]
    subject_id: str
    subject_type: str
    title: str
    summary: dict = Field(default_factory=dict)
    claims: list[dict] = Field(default_factory=list)
    observations: list[dict] = Field(default_factory=list)
    evidence: list[dict] = Field(default_factory=list)
    relations: list[dict] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


def _safe_get(world: ArchitectureQueryPort, object_id: str) -> dict | None:
    try:
        return world.get_object(object_id)
    except KeyError:
        return None


def _resolve(world: ArchitectureQueryPort, subject: str) -> dict | None:
    """ById first, then by name/content across the interesting types.
    Evidence objects resolve by id only; relations resolve by id."""
    obj = _safe_get(world, subject)
    if obj:
        return obj
    for obj_type, match in (("architecture_element", {"name": subject}),
                            ("claim", None),
                            ("observation", {"subject": subject})):
        found = world.find_objects(obj_type, **(match or {}))
        if obj_type == "claim":
            found = [c for c in found if subject in
                     (c["data"].get("subjects") or [])]
        if found:
            return found[0]
    # relations last: ids live outside the object store (rel_001 …)
    for rel in world.architecture_relations():
        if rel["id"] == subject:
            return {"id": rel["id"], "type": "architecture_relation",
                    "data": {"kind": rel["kind"], "source": rel["source"],
                             "target": rel["target"],
                             **(rel.get("data") or {})}}
    return None


def _claim_summary(world: ArchitectureQueryPort, obj: dict) -> dict:
    data = obj["data"]
    return {
        "id": obj["id"],
        "statement": data.get("statement", ""),
        "status": data.get("status", ""),
        "contradicted": world.claim_is_contradicted(obj["id"]),
    }


def _evidence_of_claim(world: ArchitectureQueryPort,
                       claim: dict) -> list[dict]:
    out: list[dict] = []
    for ref in claim["data"].get("evidence_refs") or []:
        ev = _safe_get(world, ref)
        if ev:
            out.append(ev)
    return out


def explain(world: ArchitectureQueryPort, subject: str) -> Explanation:
    obj = _resolve(world, subject)
    if obj is None:
        raise SubjectNotFound(
            f"no element, claim, observation or evidence matches {subject!r}")
    obj_type = obj["type"]
    data = obj["data"]
    base = {
        "subject_id": obj["id"],
        "subject_type": obj_type,
        "title": data.get("name") or data.get("statement")
        or data.get("subject") or obj["id"],
        "summary": data,
    }
    gaps: list[str] = []

    if obj_type == "architecture_element":
        relations = [r for r in world.architecture_relations()
                     if obj["id"] in (r["source"], r["target"])]
        claims = [c for c in world.find_objects("claim")
                  if data.get("name") in (c["data"].get("subjects") or [])]
        if not claims:
            gaps.append("element has no claim lineage recorded")
        return Explanation(**base, claims=[_claim_summary(world, c)
                                           for c in claims],
                           relations=relations, gaps=gaps)

    if obj_type == "claim":
        observations = []
        evidence = _evidence_of_claim(world, obj)
        for oid in world.claim_observation_ids(obj["id"]):
            obs = _safe_get(world, oid)
            if obs is None:
                gaps.append(f"observation {oid} is missing")
            else:
                observations.append(obs)
        if not evidence:
            gaps.append("claim has no evidence references")
        return Explanation(**base,
                           claims=[_claim_summary(world, obj)],
                           observations=observations, evidence=evidence,
                           gaps=gaps)

    if obj_type == "observation":
        claims = [c for c in world.find_objects("claim")
                  if obj["id"] in world.claim_observation_ids(c["id"])]
        embedded = data.get("evidence") or {}
        evidence = [{"id": "", "type": "evidence", "data": embedded}] \
            if embedded else []
        if not evidence:
            gaps.append("observation carries no embedded evidence")
        return Explanation(**base,
                           claims=[_claim_summary(world, c) for c in claims],
                           evidence=evidence, gaps=gaps)

    if obj_type == "architecture_relation":
        def _name(endpoint: str) -> str:
            endpoint_obj = _safe_get(world, endpoint)
            if endpoint_obj:
                return endpoint_obj["data"].get("name") or endpoint
            return endpoint

        title = (f"{_name(obj['data']['source'])}"
                 f" -[{obj['data']['kind']}]->"
                 f" {_name(obj['data']['target'])}")
        return Explanation(subject_id=obj["id"],
                           subject_type="architecture_relation",
                           title=title, summary=obj["data"],
                           relations=[obj["data"]],
                           gaps=["relation has no claim lineage recorded"])

    # evidence
    claims = [c for c in world.find_objects("claim")
              if obj["id"] in (c["data"].get("evidence_refs") or [])]
    if not claims:
        gaps.append("no claim references this evidence")
    return Explanation(**base,
                       claims=[_claim_summary(world, c) for c in claims],
                       gaps=gaps)
