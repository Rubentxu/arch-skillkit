"""Context Compiler (Phase D, docs/v2/06-context-compiler.md).

Turns a goal (+optional subject) into a budgeted ContextPack assembled
from the Architecture World and the Code Index. Principle: más grafo no
significa mejor contexto — the compiler ranks, expands one bounded hop
and then enforces the budget (UAT2-007). Source files are only opened
for locations already resolved by the Code Index (UAT2-008); missing
sources degrade to uncertainties, never to speculative reads.

The compiler is read-only: compiling never mutates the world.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from archskillkit.codeindex import CodeIndex
from archskillkit.world import ArchitectureWorld

SNIPPET_CONTEXT_LINES = 3


class Budget(BaseModel):
    """design/schemas/context-pack.yaml#budget."""

    model_config = ConfigDict(extra="forbid")

    max_nodes: int = Field(default=50, ge=0)
    max_edges: int = Field(default=100, ge=0)
    max_source_lines: int = Field(default=200, ge=0)


class ContextPack(BaseModel):
    """design/schemas/context-pack.yaml + context-read metrics (M2-D4)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    goal: str
    intent: str = "overview"
    summary: str = ""
    architecture: dict = Field(default_factory=lambda: {"elements": [], "relations": []})
    code: dict = Field(default_factory=lambda: {"symbols": [], "paths": []})
    evidence: list = Field(default_factory=list)
    source_snippets: list = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    budget: Budget = Field(default_factory=Budget)
    metrics: dict[str, int] = Field(default_factory=dict)


def classify_intent(goal: str) -> str:
    """Deterministic intent classification (pipeline step 1)."""
    text = goal.lower()
    if "endpoint" in text or " api" in text or text.startswith("api"):
        return "endpoints"
    if "drift" in text or "boundary" in text or "rule" in text:
        return "drift"
    if "evidence" in text or "why" in text or "claim" in text:
        return "evidence"
    return "overview"


class ContextCompiler:
    """Assembles ContextPacks and records calls separately from source I/O.

    ``context_reads`` remains an alias for ``compiler_calls`` for consumers
    of the original metric.  ``source_file_reads`` counts successful file
    reads made while resolving snippets; it is intentionally not incremented
    for a compiler invocation that needs no source or for an unreadable path.
    """

    def __init__(self, world: ArchitectureWorld, index: CodeIndex,
                 source_root: str | Path | None = None):
        self.world = world
        self.index = index
        self.source_root = Path(source_root) if source_root else (
            Path(world.root) if world.root else None)
        self._compiler_calls = 0
        self._source_file_reads = 0
        self._source_bytes_read = 0

    def compile(self, goal: str, subject: str | None = None,
                budget: Budget | None = None) -> ContextPack:
        budget = budget or Budget()
        self._compiler_calls += 1
        intent = classify_intent(goal)
        uncertainties: list[str] = []

        # 2. resolve architecture objects
        elements = self._elements_for(subject, uncertainties)

        # 3.+4. expand one bounded hop through architecture relations
        relations = self._relations_touching({e["id"] for e in elements})
        neighbors = [e for e in self.world.find_objects("architecture_element")
                     if e["id"] in {r["source"] for r in relations}
                     | {r["target"] for r in relations}
                     and e not in elements]
        elements = self._ranked(elements) + self._ranked(neighbors)

        # 8. budget: nodes first, then relations among the kept nodes
        elements = elements[:budget.max_nodes]
        kept = {e["id"] for e in elements}
        relations = sorted(
            (r for r in relations
             if r["source"] in kept and r["target"] in kept),
            key=lambda r: (r["kind"], r["source"], r["target"]),
        )[:budget.max_edges]

        # 3b. code facts for the subject — always, so targeted snippets
        # can be resolved from index locations (UAT2-008)
        symbols: list[dict] = []
        if subject:
            symbols = self.index.search_symbol(subject, limit=budget.max_nodes)

        # 5. evidence attached to the kept relations
        evidence = self._evidence_for(relations)

        # 6.+8b. snippets from resolved locations, within the line budget
        snippets, lines_used = [], 0
        for sym in symbols:
            if lines_used >= budget.max_source_lines:
                break
            snippet, taken = self._read_snippet(sym, budget.max_source_lines
                                                - lines_used)
            if snippet is None:
                uncertainties.append(
                    f"source not available: {sym['path']}")
                continue
            snippets.append(snippet)
            lines_used += taken
        if subject and symbols and not snippets:
            uncertainties.append(
                "no source snippets: resolved locations were unreadable")

        pack = ContextPack(
            goal=goal,
            intent=intent,
            summary=(f"{intent}: {len(elements)} elements, "
                     f"{len(relations)} relations"
                     + (f", subject '{subject}'" if subject else "")),
            architecture={"elements": [
                {"id": e["id"], "name": e["data"]["name"],
                 "kind": e["data"]["kind"], "origin": e["data"]["origin"],
                 "confidence": e["data"]["confidence"]}
                for e in elements],
                "relations": [
                    {"id": r["id"], "kind": r["kind"], "source": r["source"],
                     "target": r["target"], "rule": (r["data"] or {}).get("rule", "")}
                    for r in relations]},
            code={"symbols": [
                {"name": s["name"], "path": s["path"],
                 "start_line": s.get("start_line"),
                 "qualified_name": s["qualified_name"]}
                for s in symbols],
                "paths": sorted({s["path"] for s in symbols})},
            evidence=evidence,
            source_snippets=snippets,
            uncertainties=uncertainties,
            budget=budget,
            metrics={
                "elements": len(elements),
                "relations": len(relations),
                "symbols": len(symbols),
                "snippets": len(snippets),
                "source_lines": lines_used,
                "compiler_calls": self._compiler_calls,
                "source_file_reads": self._source_file_reads,
                "source_bytes_read": self._source_bytes_read,
                # Compatibility alias retained for existing metric consumers.
                "context_reads": self._compiler_calls,
            },
        )
        for el in elements:
            if el["data"].get("confidence") != "high" and \
                len(pack.uncertainties) < 8:
                pack.uncertainties.append(
                    f"low confidence element: {el['data']['name']}")
        return pack

    # ---- pipeline steps -------------------------------------------------

    def _elements_for(self, subject: str | None,
                      uncertainties: list[str]) -> list[dict]:
        elements = self.world.find_objects("architecture_element")
        if not subject:
            return elements
        exact = [e for e in elements if e["data"]["name"] == subject]
        partial = [e for e in elements
                   if subject.lower() in e["data"]["name"].lower()]
        matched = exact or partial
        if not matched:
            uncertainties.append(f"no architecture matches '{subject}'")
        return matched

    @staticmethod
    def _ranked(elements: list[dict]) -> list[dict]:
        return sorted(elements, key=lambda e: e["data"]["name"])

    def _relations_touching(self, ids: set[str]) -> list[dict]:
        return [r for r in self.world.architecture_relations()
                if r["source"] in ids or r["target"] in ids]

    def _evidence_for(self, relations: list[dict]) -> list[dict]:
        out: dict[str, dict] = {}
        for rel in relations:
            for ref in (rel["data"] or {}).get("evidence_ids", []):
                try:
                    obj = self.world.get_object(ref)
                except KeyError:
                    continue
                out[obj["id"]] = {"id": obj["id"], **obj["data"]}
        return sorted(out.values(), key=lambda e: (e.get("rule", ""), e["id"]))

    def _read_snippet(self, symbol: dict, max_lines: int) -> tuple[dict | None, int]:
        """Read a snippet ONLY at an index-resolved location (UAT2-008)."""
        start_line = symbol.get("start_line") or 1
        start = max(1, start_line - SNIPPET_CONTEXT_LINES)
        take = min(SNIPPET_CONTEXT_LINES * 2 + 1, max_lines)
        if take <= 0:
            return None, 0
        path = self.source_root / symbol["path"] if self.source_root else None
        if path is None:
            return None, 0
        try:
            lines = path.read_text().splitlines()
        except OSError:
            return None, 0
        self._source_file_reads += 1
        # ``read_text`` opens the complete file, even when the returned
        # snippet is clipped.  Stat after the successful read keeps the byte
        # metric aligned with that I/O operation and does not count failures.
        try:
            self._source_bytes_read += path.stat().st_size
        except OSError:
            # The read already succeeded; a concurrent removal must not make
            # the source-read counter inaccurate.
            pass
        end = min(len(lines), start + take - 1)
        if start_line > len(lines):
            return None, 0
        text = "\n".join(lines[start - 1:end])
        return {
            "path": symbol["path"],
            "start_line": start,
            "end_line": end,
            "symbol": symbol["name"],
            "text": text,
        }, end - start + 1
