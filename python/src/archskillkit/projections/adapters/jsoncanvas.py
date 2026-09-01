"""JSON Canvas projection adapter (V2.3-F10, docs/v2/31, docs/v2/46).

JSON Canvas 1.0 (https://jsoncanvas.org) for knowledge/notes applications
(Obsidian and friends): deterministic grid layout, one text node per
architecture element, one labelled edge per relation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from archskillkit.projections.contract import (
    ProjectionContext,
    ProjectionMetrics,
    ProjectionResult,
)
from archskillkit.projections.intents import IntentType, VisualIntent

_NODE_WIDTH = 260
_NODE_HEIGHT = 100
_COL_STEP = 300
_ROW_STEP = 130
_PER_ROW = 4


class JSONCanvasAdapter:
    name = "jsoncanvas"
    supported_intents = frozenset(
        {"knowledge_map", "proposal_board", "investigation"}
        & set(IntentType.__args__))  # type: ignore[attr-defined]
    version = "0.1.0"

    def project(self, intent: VisualIntent,
                context: ProjectionContext) -> ProjectionResult:
        artifact = context.annotations.get("artifact")
        if not artifact:
            raise ValueError(
                "jsoncanvas adapter requires annotations['artifact']")
        snap = context.snapshot
        elements: list[dict[str, Any]] = sorted(
            snap.get("elements", []), key=lambda e: e["name"])
        relations: list[dict[str, Any]] = sorted(
            snap.get("relations", []),
            key=lambda r: (r["kind"], r["source"], r["target"]))

        canvas: dict[str, Any] = {"version": "1.0", "nodes": [], "edges": []}
        ids: dict[str, str] = {}
        for index, element in enumerate(elements):
            node_id = f"n{index}"
            ids[element["name"]] = node_id
            canvas["nodes"].append({
                "id": node_id,
                "type": "text",
                "x": (index % _PER_ROW) * _COL_STEP,
                "y": (index // _PER_ROW) * _ROW_STEP,
                "width": _NODE_WIDTH,
                "height": _NODE_HEIGHT,
                "text": (f"**{element['name']}**\n{element['kind']}"
                         f" · {element['origin']}"
                         f" / confidence {element['confidence']}"),
            })

        rendered_edges = 0
        for index, relation in enumerate(relations):
            src = ids.get(relation["source"])
            dst = ids.get(relation["target"])
            if not src or not dst:
                continue
            canvas["edges"].append({
                "id": f"e{index}", "fromNode": src, "toNode": dst,
                "label": relation["kind"],
            })
            rendered_edges += 1

        path = Path(artifact)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(canvas, indent=2) + "\n")

        return ProjectionResult(
            format=self.name,
            path=str(path),
            source_snapshot={
                "architecture_run": context.architecture_run,
                "code_index_revision": context.code_index_revision,
            },
            metrics=ProjectionMetrics(nodes=len(ids), edges=rendered_edges),
        )
