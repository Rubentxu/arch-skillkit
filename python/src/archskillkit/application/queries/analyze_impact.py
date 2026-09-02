"""AnalyzeImpact use case (V2.4 M2, docs/v2/67 slice 7).

"What breaks if this changes?" for the three subject kinds the M2 gate
requires — file, symbol and element. Traversal is deliberately bounded:
CodeIndex lookup (symbols of a file, symbol resolution) plus one hop of
architecture relations and their evidence. Deeper call-graph ripples
are a future refinement driven by real UAT cases, not speculation.
Read-only: analysis never mutates the world.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from archskillkit.codeindex import AmbiguousSymbolError

IMPACT_SCHEMA = "arch-skillkit/impact-result-v1"

ImpactKind = Literal["file", "symbol", "element"]


class ImpactResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema: Literal["arch-skillkit/impact-result-v1"] = IMPACT_SCHEMA  # type: ignore[assignment]
    kind: ImpactKind
    value: str
    resolved: bool = False
    elements: list[dict] = Field(default_factory=list)
    relations: list[dict] = Field(default_factory=list)
    symbols: list[dict] = Field(default_factory=list)
    paths: list[str] = Field(default_factory=list)
    evidence: list[dict] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class _Collector:
    """Accumulates the impact closure without duplicates."""

    def __init__(self) -> None:
        self.element_ids: dict[str, dict] = {}
        self.relation_ids: dict[str, dict] = {}
        self.symbol_keys: dict[tuple, dict] = {}
        self.paths: dict[str, None] = {}
        self.evidence_ids: dict[str, dict] = {}
        self.gaps: list[str] = []

    def add_element(self, obj: dict) -> None:
        data = obj["data"]
        self.element_ids[obj["id"]] = {
            "id": obj["id"], "name": data.get("name"),
            "kind": data.get("kind")}

    def add_relation(self, rel: dict) -> None:
        self.relation_ids[rel["id"]] = {
            "id": rel["id"], "kind": rel["kind"], "source": rel["source"],
            "target": rel["target"]}

    def add_symbol(self, sym: dict) -> None:
        key = (sym.get("path"), sym.get("name"), sym.get("start_line"))
        self.symbol_keys[key] = {
            "name": sym.get("name"), "path": sym.get("path"),
            "start_line": sym.get("start_line")}
        if sym.get("path"):
            self.paths[sym["path"]] = None

    def add_evidence(self, obj: dict) -> None:
        self.evidence_ids[obj["id"]] = {"id": obj["id"], **obj["data"]}


def _elements_matching(world, needle: str) -> list[dict]:
    elements = world.find_objects("architecture_element")
    exact = [e for e in elements if e["data"].get("name") == needle]
    if exact:
        return exact
    return [e for e in elements
            if needle.lower() in e["data"].get("name", "").lower()]


def _expand_elements(world, collector: _Collector,
                     seed_ids: set[str]) -> None:
    """One bounded hop: relations touching the seeds, both endpoints,
    and the evidence carried by those relations."""
    relations = [r for r in world.architecture_relations()
                 if r["source"] in seed_ids or r["target"] in seed_ids]
    for rel in relations:
        collector.add_relation(rel)
        for endpoint in (rel["source"], rel["target"]):
            try:
                collector.add_element(world.get_object(endpoint))
            except KeyError:
                collector.gaps.append(f"element missing: {endpoint}")
        for ref in (rel.get("data") or {}).get("evidence_ids") or []:
            try:
                collector.add_evidence(world.get_object(ref))
            except KeyError:
                collector.gaps.append(f"evidence missing: {ref}")


def _impact_for_paths(world, index, collector: _Collector,
                      paths: set[str]) -> None:
    """Architecture knowledge that references the changed files:
    evidence living there pins the relations and elements affected."""
    for rel in world.architecture_relations():
        for ref in (rel.get("data") or {}).get("evidence_ids") or []:
            try:
                ev = world.get_object(ref)
            except KeyError:
                continue
            if ev["data"].get("file") in paths:
                collector.add_relation(rel)
                collector.add_evidence(ev)
                for endpoint in (rel["source"], rel["target"]):
                    try:
                        collector.add_element(world.get_object(endpoint))
                    except KeyError:
                        collector.gaps.append(
                            f"element missing: {endpoint}")


def analyze_impact(world, index, kind: ImpactKind, value: str,
                   ) -> ImpactResult:
    result = ImpactResult(kind=kind, value=value)
    collector = _Collector()

    if kind == "file":
        collector.paths[value] = None  # the changed file is the subject
        symbols = index.symbols_in_file(value)
        for sym in symbols:
            collector.add_symbol(sym)
        if not symbols:
            collector.gaps.append(f"file not in code index: {value}")
        _impact_for_paths(world, index, collector, {value})
        result.resolved = bool(symbols) or bool(collector.relation_ids)

    elif kind == "symbol":
        try:
            resolved = index.resolve(value)
        except AmbiguousSymbolError:
            resolved = None  # ambiguous or unknown: fall back to FTS search
        matches = [resolved] if resolved else index.search_symbol(value,
                                                                  limit=50)
        for sym in matches:
            collector.add_symbol(sym)
        if not matches:
            collector.gaps.append(f"symbol not in code index: {value}")
        for element in _elements_matching(world, value):
            collector.add_element(element)
        seed_ids = set(collector.element_ids)
        if seed_ids:
            _expand_elements(world, collector, seed_ids)
        _impact_for_paths(world, index, collector,
                          set(collector.paths))
        result.resolved = bool(matches) or bool(collector.element_ids)

    else:  # element
        matches = _elements_matching(world, value)
        if not matches:
            try:
                obj = world.get_object(value)
            except KeyError:
                obj = None
            if obj and obj["type"] == "architecture_element":
                matches = [obj]
        if not matches:
            collector.gaps.append(f"no architecture element matches: {value}")
        for element in matches:
            collector.add_element(element)
        seed_ids = set(collector.element_ids)
        if seed_ids:
            _expand_elements(world, collector, seed_ids)
        for element_id in seed_ids:
            try:
                element = world.get_object(element_id)
            except KeyError:
                continue
            for sym in index.search_symbol(
                    element["data"].get("name", ""), limit=20):
                collector.add_symbol(sym)
        result.resolved = bool(matches)

    result.elements = sorted(collector.element_ids.values(),
                             key=lambda e: e["id"])
    result.relations = sorted(collector.relation_ids.values(),
                              key=lambda r: r["id"])
    result.symbols = sorted(collector.symbol_keys.values(),
                            key=lambda s: (s.get("path") or "",
                                           s.get("name") or ""))
    result.paths = sorted(collector.paths)
    result.evidence = sorted(collector.evidence_ids.values(),
                             key=lambda e: e["id"])
    result.gaps = collector.gaps
    return result
