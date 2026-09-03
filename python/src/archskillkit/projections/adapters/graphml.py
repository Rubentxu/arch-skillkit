"""GraphML projection adapter (V2.3-F10, docs/v2/32, docs/v2/46).

Directed GraphML for graph-analysis applications (Cytoscape, Gephi, yEd):
deterministic node/edge ordering, architecture metadata as <data> keys.
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

_GRAPHML_NS = "http://graphml.graphdrawing.org/xmlns"

_NODE_KEYS = (("d_name", "name"), ("d_kind", "kind"), ("d_origin", "origin"),
              ("d_confidence", "confidence"))
_EDGE_KEYS = (("d_relkind", "kind"), ("d_rule", "rule"),
              ("d_confidence", "confidence"))


class GraphMLAdapter:
    name = "graphml"
    supported_intents = frozenset(
        {"dependency_graph", "large_graph_analysis"}
        & set(IntentType.__args__))  # type: ignore[attr-defined]
    version = "0.2.0"  # 0.2.0: nodes carry their name (P-03 external-viewer fix)

    def project(self, intent: VisualIntent,
                context: ProjectionContext) -> ProjectionResult:
        artifact = context.annotations.get("artifact")
        if not artifact:
            raise ValueError("graphml adapter requires annotations['artifact']")
        snap = context.snapshot
        elements: list[dict[str, Any]] = sorted(
            snap.get("elements", []), key=lambda e: e["name"])
        relations: list[dict[str, Any]] = sorted(
            snap.get("relations", []),
            key=lambda r: (r["kind"], r["source"], r["target"]))

        root = ET.Element("graphml", {"xmlns": _GRAPHML_NS})
        for key_id, attr_name in _NODE_KEYS:
            ET.SubElement(root, "key", {"id": key_id, "for": "node",
                                        "attr.name": attr_name,
                                        "attr.type": "string"})
        for key_id, attr_name in _EDGE_KEYS:
            ET.SubElement(root, "key", {"id": key_id, "for": "edge",
                                        "attr.name": attr_name,
                                        "attr.type": "string"})
        graph = ET.SubElement(root, "graph",
                              {"id": "G", "edgedefault": "directed"})

        ids: dict[str, str] = {}
        for index, element in enumerate(elements):
            node_id = f"n{index}"
            ids[element["name"]] = node_id
            node = ET.SubElement(graph, "node", {"id": node_id})
            for key_id, attr_name in _NODE_KEYS:
                ET.SubElement(node, "data", {"key": key_id}).text = \
                    str(element.get(attr_name, ""))

        rendered_edges = 0
        for index, relation in enumerate(relations):
            src = ids.get(relation["source"])
            dst = ids.get(relation["target"])
            if not src or not dst:
                continue
            edge = ET.SubElement(graph, "edge", {
                "id": f"e{index}", "source": src, "target": dst})
            data = relation.get("data") or {}
            for key_id, attr_name in _EDGE_KEYS:
                value = (relation.get("confidence", "high")
                         if attr_name == "confidence"
                         else (relation.get("rule", "")
                               if attr_name == "rule" else relation["kind"]))
                if attr_name == "rule":
                    value = data.get("rule", "")
                ET.SubElement(edge, "data", {"key": key_id}).text = str(value)
            rendered_edges += 1

        ET.indent(root, space="  ")
        path = Path(artifact)
        path.parent.mkdir(parents=True, exist_ok=True)
        tree = ET.ElementTree(root)
        ET.register_namespace("", _GRAPHML_NS)
        tree.write(path, encoding="unicode", xml_declaration=False)

        return ProjectionResult(
            format=self.name,
            path=str(path),
            source_snapshot={
                "architecture_run": context.architecture_run,
                "code_index_revision": context.code_index_revision,
            },
            metrics=ProjectionMetrics(nodes=len(ids), edges=rendered_edges),
        )
