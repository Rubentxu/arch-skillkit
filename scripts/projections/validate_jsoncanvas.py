#!/usr/bin/env python3
"""JSON Canvas projection adapter validation (docs/v2/47 P7).

Generates the JSON Canvas 1.0 artifact from the canonical Kotlin
fixture, validates it against the public Obsidian Canvas schema
(https://jsoncanvas.org/schema/1.0), and reconciles node/edge counts
and edge endpoints with the adapter metrics. Writes evidence under
``artifacts/projections-validation/jsoncanvas/``.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

import jsonschema
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "python"))
sys.path.insert(0, str(REPO_ROOT / "python" / "tests"))

from conftest import build_kotlin_world  # noqa: E402

from archskillkit.promotion import discover  # noqa: E402
from archskillkit.projections import VisualIntent  # noqa: E402
from archskillkit.projections.adapters.jsoncanvas import JSONCanvasAdapter  # noqa: E402
from archskillkit.projections.schemas import load_schema  # noqa: E402
from archskillkit.projections.writer import project_to_workspace  # noqa: E402


def main() -> int:
    out_root = REPO_ROOT / "artifacts" / "projections-validation" / "jsoncanvas"
    out_root.mkdir(parents=True, exist_ok=True)
    artifact = out_root / "kotlin-world.canvas.json"

    with tempfile.TemporaryDirectory(prefix="ark-p7-canvas-") as tmp:
        sandbox = Path(tmp)
        os.environ["XDG_DATA_HOME"] = str(sandbox / "data")
        os.environ["XDG_STATE_HOME"] = str(sandbox / "state")
        repo = sandbox / "kotlin-demo"
        world, index = build_kotlin_world(repo)
        discover(world, index, scan_run_id="scan-1")
        result = project_to_workspace(
            world, JSONCanvasAdapter(),
            intent=VisualIntent(type="knowledge_map", subject="x"))
        produced = Path(result["path"])
        artifact.write_bytes(produced.read_bytes())
        metrics = {
            "adapter_nodes": result["metrics"]["nodes"],
            "adapter_edges": result["metrics"]["edges"],
        }
        index.close()
        world.close()

    canvas = json.loads(artifact.read_text())
    sha256 = hashlib.sha256(artifact.read_bytes()).hexdigest()

    validator = Draft202012Validator(load_schema("jsoncanvas-1.0"))
    schema_errors = sorted(validator.iter_errors(canvas), key=lambda e: e.path)

    parsed_nodes = len(canvas.get("nodes", []))
    parsed_edges = len(canvas.get("edges", []))
    node_ids = {n["id"] for n in canvas.get("nodes", [])}
    dangling_edges = [
        e for e in canvas.get("edges", [])
        if e.get("fromNode") not in node_ids or e.get("toNode") not in node_ids
    ]
    edges_without_label = [e for e in canvas.get("edges", []) if not e.get("label")]

    reconciliation = {
        "adapter_metrics": metrics,
        "parsed_nodes": parsed_nodes,
        "parsed_edges": parsed_edges,
        "version": canvas.get("version"),
        "schema_errors": [
            f"{'/'.join(str(p) for p in err.absolute_path)}: {err.message}"
            for err in schema_errors
        ],
        "dangling_edges": dangling_edges,
        "edges_without_label": edges_without_label,
        "artifact_sha256": sha256,
    }
    (out_root / "reconciliation.json").write_text(
        json.dumps(reconciliation, indent=2, sort_keys=True)
    )

    fail: list[str] = []
    if schema_errors:
        fail.append(
            f"schema validation: {len(schema_errors)} error(s) — "
            f"see reconciliation.json"
        )
    if parsed_nodes != metrics["adapter_nodes"]:
        fail.append(
            f"node count mismatch: adapter={metrics['adapter_nodes']} "
            f"canvas={parsed_nodes}"
        )
    if parsed_edges != metrics["adapter_edges"]:
        fail.append(
            f"edge count mismatch: adapter={metrics['adapter_edges']} "
            f"canvas={parsed_edges}"
        )
    if dangling_edges:
        fail.append(
            f"{len(dangling_edges)} edge(s) point to non-existent nodes"
        )
    if edges_without_label:
        fail.append(
            f"{len(edges_without_label)} edge(s) without label"
        )

    summary = out_root / "summary.md"
    lines = [
        "# JSON Canvas adapter — P7 validation evidence",
        "",
        f"- Artifact: `{artifact.relative_to(REPO_ROOT)}`",
        f"- SHA-256: `{sha256}`",
        f"- Adapter metrics: {metrics}",
        f"- Canvas parsed: nodes={parsed_nodes}, edges={parsed_edges}",
        f"- Version: `{canvas.get('version')}`",
        f"- Schema: JSON Canvas 1.0 (https://jsoncanvas.org/schema/1.0)",
        "",
        "## Verdict",
        "",
        ("PASS — JSON Canvas 1.0 schema valid; node/edge counts match "
         "adapter metrics; every edge points to a real node and "
         "carries a label." if not fail else "FAIL — see reconciliation.json."),
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