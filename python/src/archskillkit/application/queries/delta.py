"""ArchitectureDelta read model (V2.4 M3, ADR-0033,
design/schemas/v2.4/architecture-delta.yaml).

Compares two world states (base vs head — main world vs a proposal
fork, or two runs) into a stable, schema-bound delta. Identity rules:
elements by name (the domain dedups by name), relations by
(kind, source name, target name). Unknown counts reuse the M2 coverage
baseline semantics (element without an accepted claim). Deterministic:
same states, same delta, byte for byte (golden-tested).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DELTA_SCHEMA = "arch-skillkit/architecture-delta-v1"


class DeltaLists(BaseModel):
    model_config = ConfigDict(extra="forbid")

    added: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)
    changed: list[str] = Field(default_factory=list)


class ArchitectureDelta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema: Literal["arch-skillkit/architecture-delta-v1"] = DELTA_SCHEMA  # type: ignore[assignment]
    base_snapshot: str
    head_snapshot: str
    elements: DeltaLists = Field(default_factory=DeltaLists)
    relations: DeltaLists = Field(default_factory=DeltaLists)
    unknowns: dict = Field(default_factory=dict)
    drift: dict = Field(default_factory=dict)
    policy_impacts: list[dict] = Field(default_factory=list)


def _state_view(world) -> tuple[dict, dict, int, int]:
    """(elements by name, relations by identity key, findings, unknowns)"""
    elements: dict[str, dict] = {}
    for obj in world.find_objects("architecture_element"):
        elements[obj["data"]["name"]] = obj["data"]
    relations: dict[tuple, dict] = {}
    for rel in world.architecture_relations():
        try:
            source = world.get_object(rel["source"])["data"]["name"]
            target = world.get_object(rel["target"])["data"]["name"]
        except KeyError:
            continue
        relations[(rel["kind"], source, target)] = rel.get("data") or {}
    accepted_subjects: set[str] = set()
    for claim in world.find_objects("claim"):
        if claim["data"].get("status") == "accepted":
            accepted_subjects.update(claim["data"].get("subjects") or [])
    unknowns = sum(1 for name in elements if name not in accepted_subjects)
    return elements, relations, len(world.findings()), unknowns


def compute_delta(base, head, base_snapshot_id: str = "",
                  head_snapshot_id: str = "") -> ArchitectureDelta:
    base_elements, base_relations, base_findings, base_unknowns = \
        _state_view(base)
    head_elements, head_relations, head_findings, head_unknowns = \
        _state_view(head)

    delta = ArchitectureDelta(base_snapshot=base_snapshot_id,
                              head_snapshot=head_snapshot_id)

    for name in sorted(head_elements.keys() - base_elements.keys()):
        delta.elements.added.append(name)
    for name in sorted(base_elements.keys() - head_elements.keys()):
        delta.elements.removed.append(name)
    for name in sorted(base_elements.keys() & head_elements.keys()):
        old, new = base_elements[name], head_elements[name]
        if any(old.get(k) != new.get(k)
               for k in ("kind", "origin", "confidence")):
            delta.elements.changed.append(name)

    for key in sorted(head_relations.keys() - base_relations.keys()):
        delta.relations.added.append(_key_str(key))
    for key in sorted(base_relations.keys() - head_relations.keys()):
        delta.relations.removed.append(_key_str(key))
    for key in sorted(base_relations.keys() & head_relations.keys()):
        old, new = base_relations[key], head_relations[key]
        if (old.get("rule", "") != new.get("rule", "")
                or old.get("evidence_ids", [])
                != new.get("evidence_ids", [])):
            delta.relations.changed.append(_key_str(key))

    delta.unknowns = {"base": base_unknowns, "head": head_unknowns,
                      "delta": head_unknowns - base_unknowns}
    delta.drift = {"findings_base": base_findings,
                   "findings_head": head_findings,
                   "delta": head_findings - base_findings}
    return delta


def _key_str(key: tuple) -> str:
    return f"{key[1]} -[{key[0]}]-> {key[2]}"
