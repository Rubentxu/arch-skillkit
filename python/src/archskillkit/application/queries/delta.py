"""ArchitectureDelta read model (V2.4 M3, ADR-0033,
design/schemas/v2.4/architecture-delta.yaml).

Compares two world states (base vs head — main world vs a proposal
fork, two runs, or two pre-built snapshot files) into a stable,
schema-bound delta. Identity rules: elements by name (the domain
dedups by name), relations by (kind, source name, target name).
Unknown counts reuse the M2 coverage baseline semantics (element
without an accepted claim). Deterministic: same states, same delta,
byte for byte (golden-tested).

The state is captured once via SnapshotState.from_world, which makes
the comparison pure (no live world dependency in the diff logic).
That also lets the CLI compare pre-built JSON state files from CI
without an open world.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

DELTA_SCHEMA = "arch-skillkit/architecture-delta-v1"
STATE_SCHEMA = "arch-skillkit/snapshot-state-v1"


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


@dataclass(frozen=True)
class SnapshotState:
    """Frozen view of the world bits that the delta cares about.

    Equality is structural so two states built from the same data
    compare equal; that is what makes the comparison pure."""

    elements: tuple[tuple[str, dict[str, Any]], ...]
    relations: frozenset[tuple[str, str, str]]
    unknowns: frozenset[str]
    findings: tuple[dict[str, Any], ...]
    rules: tuple[dict[str, Any], ...]

    def __post_init__(self) -> None:
        # Canonical order so two states built from the same data
        # compare equal regardless of caller order.
        object.__setattr__(
            self, "elements",
            tuple(sorted(self.elements, key=lambda pair: pair[0])))
        object.__setattr__(
            self, "findings", tuple(self.findings))
        object.__setattr__(
            self, "rules", tuple(self.rules))

    @classmethod
    def from_world(cls, world) -> SnapshotState:
        elements: list[tuple[str, dict[str, Any]]] = []
        for obj in world.find_objects("architecture_element"):
            data = obj["data"]
            elements.append((data["name"], dict(data)))
        relations: set[tuple[str, str, str]] = set()
        for rel in world.architecture_relations():
            try:
                source = world.get_object(rel["source"])["data"]["name"]
                target = world.get_object(rel["target"])["data"]["name"]
            except KeyError:
                continue
            relations.add((rel["kind"], source, target))
        accepted_subjects: set[str] = set()
        for claim in world.find_objects("claim"):
            if claim["data"].get("status") == "accepted":
                accepted_subjects.update(claim["data"].get("subjects") or [])
        all_names = {n for n, _ in elements}
        unknowns = all_names - accepted_subjects
        return cls(
            elements=tuple(sorted(elements)),
            relations=frozenset(relations),
            unknowns=frozenset(unknowns),
            findings=tuple(_finding_data(f) for f in world.findings()),
            rules=tuple(_rule_data(r) for r in world.architecture_rules()),
        )

    def to_json(self) -> str:
        return json.dumps({
            "schema": STATE_SCHEMA,
            "elements": [{"name": n, **attrs} for n, attrs in self.elements],
            "relations": [{"kind": k, "source": s, "target": t}
                          for k, s, t in sorted(self.relations)],
            "unknowns": sorted(self.unknowns),
            "findings": list(self.findings),
            "rules": list(self.rules),
        }, indent=2, sort_keys=True) + "\n"

    @classmethod
    def from_json(cls, payload: str | dict) -> SnapshotState:
        data = json.loads(payload) if isinstance(payload, str) else payload
        elements: list[tuple[str, dict[str, Any]]] = []
        for e in data.get("elements", []):
            name = e["name"]
            attrs = {k: v for k, v in e.items() if k != "name"}
            elements.append((name, attrs))
        relations = frozenset(
            (r["kind"], r["source"], r["target"])
            for r in data.get("relations", []))
        return cls(
            elements=tuple(elements),
            relations=relations,
            unknowns=frozenset(data.get("unknowns", [])),
            findings=tuple(data.get("findings", [])),
            rules=tuple(data.get("rules", [])),
        )


def _finding_data(f: dict) -> dict:
    return dict(f.get("data") or {})


def _rule_data(r: dict) -> dict:
    return dict(r.get("data") or r or {})


def _state_view(world) -> tuple[dict, dict, int, int]:
    """Legacy view kept for the world-vs-world API below."""
    state = SnapshotState.from_world(world)
    elements = {n: a for n, a in state.elements}
    relations = {key: {} for key in state.relations}
    return (elements, relations,
            len(state.findings), len(state.unknowns))


def compute_delta(base, head, base_snapshot_id: str = "",
                  head_snapshot_id: str = "") -> ArchitectureDelta:
    return compute_delta_states(
        SnapshotState.from_world(base),
        SnapshotState.from_world(head),
        base_snapshot_id=base_snapshot_id,
        head_snapshot_id=head_snapshot_id,
    )


def compute_delta_states(base: SnapshotState, head: SnapshotState,
                         base_snapshot_id: str = "",
                         head_snapshot_id: str = "") -> ArchitectureDelta:
    delta = ArchitectureDelta(base_snapshot=base_snapshot_id,
                              head_snapshot=head_snapshot_id)

    base_elements = {n: a for n, a in base.elements}
    head_elements = {n: a for n, a in head.elements}
    for name in sorted(head_elements.keys() - base_elements.keys()):
        delta.elements.added.append(name)
    for name in sorted(base_elements.keys() - head_elements.keys()):
        delta.elements.removed.append(name)
    for name in sorted(base_elements.keys() & head_elements.keys()):
        old, new = base_elements[name], head_elements[name]
        if any(old.get(k) != new.get(k)
               for k in ("kind", "origin", "confidence")):
            delta.elements.changed.append(name)

    base_rels = base.relations
    head_rels = head.relations
    for key in sorted(head_rels - base_rels):
        delta.relations.added.append(_key_str(key))
    for key in sorted(base_rels - head_rels):
        delta.relations.removed.append(_key_str(key))
    # relations.changed requires richer state (rule/evidence refs)
    # which state files may not carry; leave empty in v1.

    delta.unknowns = {"base": len(base.unknowns),
                      "head": len(head.unknowns),
                      "delta": len(head.unknowns) - len(base.unknowns)}
    delta.drift = {"findings_base": len(base.findings),
                   "findings_head": len(base.findings),
                   "delta": len(head.findings) - len(base.findings)}
    return delta


def _key_str(key: tuple) -> str:
    return f"{key[1]} -[{key[0]}]-> {key[2]}"
