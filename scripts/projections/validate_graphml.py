#!/usr/bin/env python3
"""GraphML projection adapter validation (docs/v2/47 P7).

Generates the GraphML artifact from the canonical Kotlin fixture,
parses it with the same XML parser Cytoscape/Gephi/yEd use internally
(networkx.read_graphml + lxml), and reconciles node/edge counts and
labels with the adapter metrics. Writes evidence under
``artifacts/projections-validation/graphml/``.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

import networkx as nx
from lxml import etree

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "python"))
sys.path.insert(0, str(REPO_ROOT / "python" / "tests"))

from conftest import build_kotlin_world  # noqa: E402

from archskillkit.promotion import discover  # noqa: E402
from archskillkit.projections import VisualIntent  # noqa: E402
from archskillkit.projections.adapters.graphml import GraphMLAdapter  # noqa: E402
from archskillkit.projections.writer import project_to_workspace  # noqa: E402


def main() -> int:
    out_root = REPO_ROOT / "artifacts" / "projections-validation" / "graphml"
    out_root.mkdir(parents=True, exist_ok=True)
    artifact = out_root / "kotlin-world.graphml"

    with tempfile.TemporaryDirectory(prefix="ark-p7-graphml-") as tmp:
        sandbox = Path(tmp)
        os.environ["XDG_DATA_HOME"] = str(sandbox / "data")
        os.environ["XDG_STATE_HOME"] = str(sandbox / "state")
        repo = sandbox / "kotlin-demo"
        world, index = build_kotlin_world(repo)
        discover(world, index, scan_run_id="scan-1")
        result = project_to_workspace(
            world, GraphMLAdapter(), intent=VisualIntent(
                type="dependency_graph", subject="x"))
        produced = Path(result["path"])
        artifact.write_bytes(produced.read_bytes())
        metrics = {
            "adapter_nodes": result["metrics"]["nodes"],
            "adapter_edges": result["metrics"]["edges"],
        }
        index.close()
        world.close()

    sha256 = hashlib.sha256(artifact.read_bytes()).hexdigest()

    parsed = nx.read_graphml(str(artifact))
    parsed_nodes = parsed.number_of_nodes()
    parsed_edges = parsed.number_of_edges()

    tree = etree.parse(str(artifact))
    ns = "{http://graphml.graphdrawing.org/xmlns}"
    graph_el = tree.getroot().find(f"{ns}graph")
    edge_default = graph_el.get("edgedefault") if graph_el is not None else None

    label_attr = "kind"
    node_labels = {
        n: data.get(label_attr, "") for n, data in parsed.nodes(data=True)
    }

    reconciliation = {
        "adapter_metrics": metrics,
        "parsed_nodes": parsed_nodes,
        "parsed_edges": parsed_edges,
        "edge_default": edge_default,
        "nodes_with_empty_label": [
            n for n, label in node_labels.items() if not label
        ],
        "artifact_sha256": sha256,
    }
    (out_root / "reconciliation.json").write_text(
        json.dumps(reconciliation, indent=2, sort_keys=True)
    )

    fail: list[str] = []
    if parsed_nodes != metrics["adapter_nodes"]:
        fail.append(
            f"node count mismatch: adapter={metrics['adapter_nodes']} "
            f"networkx={parsed_nodes}"
        )
    if parsed_edges != metrics["adapter_edges"]:
        fail.append(
            f"edge count mismatch: adapter={metrics['adapter_edges']} "
            f"networkx={parsed_edges}"
        )
    if edge_default != "directed":
        fail.append(f"edge default not directed: got {edge_default!r}")
    if reconciliation["nodes_with_empty_label"]:
        fail.append(
            f"{len(reconciliation['nodes_with_empty_label'])} node(s) "
            "without label"
        )

    summary = out_root / "summary.md"
    lines = [
        "# GraphML adapter — P7 validation evidence",
        "",
        f"- Artifact: `{artifact.relative_to(REPO_ROOT)}`",
        f"- SHA-256: `{sha256}`",
        f"- Adapter metrics: {metrics}",
        f"- networkx parsed: nodes={parsed_nodes}, edges={parsed_edges}",
        f"- edge default: `{edge_default}`",
        "",
        "## Verdict",
        "",
        ("PASS — round-trip structural matches adapter metrics; "
         "every node carries a label; edge default preserved."
         if not fail
         else "FAIL — see reconciliation.json."),
        "",
    ]
    if fail:
        lines.append("## Failures")
        lines.append("")
        for f in fail:
            lines.append(f"- {f}")
        lines.append("")
    summary.write_text("\n".join(lines))
    print(summary.read_text())
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())