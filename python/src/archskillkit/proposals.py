"""Phase G — fork/diff of the architecture (docs/v2/08, M2-G3/G4).

`structural_diff` compares the architecture layers of two world runs by
semantic names (never by runtime ids) and reports additions, removals,
confidence changes and findings that appeared or resolved.
`promote` applies an approved proposal's diff to the main world —
refused without approval (UAT2-014) and idempotent.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from archskillkit.world import ArchitectureWorld, PromotionError


class PromotionRequired(PromotionError):
    """Promotion was attempted without an approved proposal (UAT2-014)."""


@dataclass
class StructuralDiff:
    elements_added: list[str] = field(default_factory=list)
    elements_removed: list[str] = field(default_factory=list)
    relations_added: list[dict] = field(default_factory=list)
    relations_removed: list[dict] = field(default_factory=list)
    confidence_changed: list[dict] = field(default_factory=list)
    evidence_changed: list[dict] = field(default_factory=list)
    findings_new: list[dict] = field(default_factory=list)
    findings_resolved: list[dict] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (self.elements_added or self.elements_removed
                    or self.relations_added or self.relations_removed
                    or self.confidence_changed or self.evidence_changed
                    or self.findings_new or self.findings_resolved)


def _arch_view(world: ArchitectureWorld):
    """Architecture layers keyed by semantic names, not runtime ids."""
    elements = {o["data"]["name"]: o["data"]
                for o in world.find_objects("architecture_element")}
    id_to_name = {o["id"]: o["data"]["name"]
                  for o in world.find_objects("architecture_element")}
    relations = {}
    for rel in world.architecture_relations():
        key = (rel["kind"], id_to_name.get(rel["source"], rel["source"]),
               id_to_name.get(rel["target"], rel["target"]))
        relations[key] = rel["data"] or {}
    findings = {(f["data"]["kind"], f["data"]["detail"]): f["data"]
                for f in world.find_objects("finding")}
    return elements, relations, findings


def structural_diff(main: ArchitectureWorld,
                    proposal: ArchitectureWorld) -> StructuralDiff:
    main_elements, main_relations, main_findings = _arch_view(main)
    fork_elements, fork_relations, fork_findings = _arch_view(proposal)

    diff = StructuralDiff()
    diff.elements_added = sorted(fork_elements.keys() - main_elements.keys())
    diff.elements_removed = sorted(main_elements.keys() - fork_elements.keys())
    for name in sorted(main_elements.keys() & fork_elements.keys()):
        if main_elements[name]["confidence"] != fork_elements[name]["confidence"]:
            diff.confidence_changed.append({
                "element": name,
                "from": main_elements[name]["confidence"],
                "to": fork_elements[name]["confidence"],
            })
    for key in sorted(fork_relations.keys() - main_relations.keys()):
        diff.relations_added.append(
            {"kind": key[0], "source": key[1], "target": key[2],
             "data": fork_relations[key]})
    for key in sorted(main_relations.keys() - fork_relations.keys()):
        diff.relations_removed.append(
            {"kind": key[0], "source": key[1], "target": key[2],
             "data": main_relations[key]})
    for key in sorted(main_relations.keys() & fork_relations.keys()):
        old, new = main_relations[key], fork_relations[key]
        if (old.get("rule", "") != new.get("rule", "")
                or old.get("evidence_ids", []) != new.get("evidence_ids", [])):
            diff.evidence_changed.append({
                "kind": key[0], "source": key[1], "target": key[2],
                "from_rule": old.get("rule", ""),
                "to_rule": new.get("rule", ""),
            })
    for key in sorted(fork_findings.keys() - main_findings.keys()):
        diff.findings_new.append({"kind": key[0], "detail": key[1]})
    for key in sorted(main_findings.keys() - fork_findings.keys()):
        diff.findings_resolved.append({"kind": key[0], "detail": key[1]})
    return diff


def promote(main: ArchitectureWorld, proposal: ArchitectureWorld) -> dict:
    """Apply an approved proposal's diff to the main world.

    Policy gate: the fork must carry a proposal object with status
    `approved` (UAT2-014). Idempotent: promoting an already-applied diff
    changes nothing.
    """
    approved = [p for p in proposal.find_objects("proposal")
                if p["data"]["status"] in ("approved", "promoted")]
    if not approved:
        raise PromotionRequired(
            "promotion requires an approved proposal in the fork (UAT2-014)")

    diff = structural_diff(main, proposal)
    summary = {"elements_added": 0, "elements_removed": 0,
               "relations_added": 0, "relations_removed": 0,
               "confidence_changed": 0}

    for name in diff.elements_added:
        data = next(o["data"] for o in
                    proposal.find_objects("architecture_element", name=name))
        main.add_architecture_element(name, data["kind"],
                                      data["origin"], data["confidence"])
        summary["elements_added"] += 1

    for change in diff.confidence_changed:
        element = next(o for o in
                       main.find_objects("architecture_element",
                                         name=change["element"]))
        main.graph.patch_object(element["id"],
                                {"confidence": change["to"]})
        summary["confidence_changed"] += 1

    for rel in diff.relations_added:
        src = next(o["id"] for o in main.find_objects(
            "architecture_element", name=rel["source"]))
        dst = next(o["id"] for o in main.find_objects(
            "architecture_element", name=rel["target"]))
        before = len(main.architecture_relations())
        main.add_architecture_relation(rel["kind"], src, dst, rel["data"])
        if len(main.architecture_relations()) > before:
            summary["relations_added"] += 1

    # diff.relations_removed carries semantic element NAMES; architecture
    # relations carry runtime ids. Resolve before matching, or removed
    # relations whose endpoints still exist are silently skipped (PR-3).
    main_element_names = {o["id"]: o["data"]["name"]
                          for o in main.find_objects("architecture_element")}
    for rel in diff.relations_removed:
        victim = next((r for r in main.architecture_relations()
                       if (r["kind"],
                           main_element_names.get(r["source"], r["source"]),
                           main_element_names.get(r["target"], r["target"]))
                       == (rel["kind"], rel["source"], rel["target"])), None)
        if victim is not None:
            main.graph.remove_relation(victim["id"])
            summary["relations_removed"] += 1

    for name in diff.elements_removed:
        element = next(o for o in main.find_objects(
            "architecture_element", name=name))
        main.graph.remove_object(element["id"])
        summary["elements_removed"] += 1

    proposal.graph.patch_object(approved[0]["id"], {"status": "promoted"})
    return summary
