"""draw.io projection adapter (V2.4-M5-23a, docs/v2/30, docs/v2/46).

mxGraph XML (draw.io / diagrams.net) for manual refinement: deterministic
grid layout, architecture metadata preserved via XML-valid attributes
(archskillkit-element-name, archskillkit-element-kind on UserObject for
vertices; archskillkit-relation-kind/source-name/target-name on mxCell
for edges). Editable without losing the source of truth (the world
regenerates with --force).

New XML metadata encoding (M5-23a):
  Vertices: <UserObject id label="..." archskillkit-element-name="..."
            archskillkit-element-kind="..."> wrapping <mxCell vertex="1">.
  Edges: flat <mxCell edge="1" archskillkit-relation-kind="..."
            archskillkit-relation-source-name="..."
            archskillkit-relation-target-name="...">.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from archskillkit.projections.contract import (
    ProjectionContext,
    ProjectionMetrics,
    ProjectionResult,
)
from archskillkit.projections.intents import IntentType, VisualIntent

_COL_STEP = 220
_ROW_STEP = 120
_PER_ROW = 4

# element category → draw.io style (deterministic, hand-editable)
_STYLES = {
    "system": "ellipse;fillColor=#dae8fc;strokeColor=#6c8ebf;",
    "container": "rounded=1;fillColor=#d5e8d4;strokeColor=#82b366;",
    "component": "rounded=1;fillColor=#dae8fc;strokeColor=#6c8ebf;",
    "bounded_context": "rounded=1;fillColor=#fff2cc;strokeColor=#d6b656;",
    "external_system": "ellipse;fillColor=#f8cecc;strokeColor=#b85450;",
    "datastore": "shape=cylinder3;fillColor=#ffe6cc;strokeColor=#d79b00;",
    "topic": "shape=hexagon;fillColor=#e1d5e7;strokeColor=#9673a6;",
    "interface": "rounded=1;dashed=1;fillColor=#ffe6cc;strokeColor=#d79b00;",
}


class DrawioAdapter:
    name = "drawio"
    supported_intents = frozenset({"technical_diagram"} & set(IntentType.__args__))  # type: ignore[attr-defined]
    version = "0.2.0"  # M5-23a: bumped for new XML-valid metadata encoding

    def project(self, intent: VisualIntent, context: ProjectionContext) -> ProjectionResult:
        artifact = context.annotations.get("artifact")
        if not artifact:
            raise ValueError("drawio adapter requires annotations['artifact']")
        snap = context.snapshot
        elements: list[dict[str, Any]] = sorted(snap.get("elements", []), key=lambda e: e["name"])
        relations: list[dict[str, Any]] = sorted(
            snap.get("relations", []), key=lambda r: (r["kind"], r["source"], r["target"])
        )

        mxfile = ET.Element("mxfile", {"host": "archskillkit", "version": self.version})
        diagram = ET.SubElement(mxfile, "diagram", {"id": "arch", "name": "architecture"})
        model = ET.SubElement(
            diagram,
            "mxGraphModel",
            {
                "dx": "800",
                "dy": "600",
                "grid": "1",
                "gridSize": "10",
                "page": "1",
                "pageWidth": "1169",
                "pageHeight": "826",
            },
        )
        root = ET.SubElement(model, "root")
        ET.SubElement(root, "mxCell", {"id": "0"})
        ET.SubElement(root, "mxCell", {"id": "1", "parent": "0"})

        ids: dict[str, str] = {}
        for index, element in enumerate(elements):
            node_id = f"n{index}"
            ids[element["name"]] = node_id
            label = (
                f"{element['name']} · {element['kind']}"
                f" · {element['origin']}/{element['confidence']}"
            )
            # UserObject-wrapped vertex (M5-23a: XML-valid kebab-case attrs)
            user_obj = ET.SubElement(
                root,
                "UserObject",
                {
                    "id": node_id,
                    "label": label,
                    "archskillkit-element-name": element["name"],
                    "archskillkit-element-kind": element["kind"],
                },
            )
            cell = ET.SubElement(
                user_obj,
                "mxCell",
                {
                    "vertex": "1",
                    "parent": "1",
                    "value": label,
                    "style": _STYLES.get(element["kind"], _STYLES["component"]),
                },
            )
            ET.SubElement(
                cell,
                "mxGeometry",
                {
                    "x": str((index % _PER_ROW) * _COL_STEP),
                    "y": str((index // _PER_ROW) * _ROW_STEP),
                    "width": "180",
                    "height": "60",
                    "as": "geometry",
                },
            )

        rendered_edges = 0
        for index, relation in enumerate(relations):
            src = ids.get(relation["source"])
            dst = ids.get(relation["target"])
            if not src or not dst:
                continue
            # Flat mxCell edge with XML-valid archskillkit relation attrs (M5-23a)
            cell = ET.SubElement(
                root,
                "mxCell",
                {
                    "id": f"e{index}",
                    "value": relation["kind"],
                    "style": "edgeStyle=orthogonalEdgeStyle;",
                    "edge": "1",
                    "parent": "1",
                    "source": src,
                    "target": dst,
                    "archskillkit-relation-kind": relation["kind"],
                    "archskillkit-relation-source-name": relation["source"],
                    "archskillkit-relation-target-name": relation["target"],
                },
            )
            ET.SubElement(cell, "mxGeometry", {"relative": "1", "as": "geometry"})
            rendered_edges += 1

        path = Path(artifact)
        path.parent.mkdir(parents=True, exist_ok=True)
        ET.indent(mxfile, space="  ")
        path.write_text(ET.tostring(mxfile, encoding="unicode"))

        return ProjectionResult(
            format=self.name,
            path=str(path),
            source_snapshot={
                "architecture_run": context.architecture_run,
                "code_index_revision": context.code_index_revision,
            },
            metrics=ProjectionMetrics(nodes=len(ids), edges=rendered_edges),
        )
