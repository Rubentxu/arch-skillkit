#!/usr/bin/env python3
"""Arrows projection adapter validation (docs/v2/47 P7).

Generates the `arch-skillkit/arrows-v1` JSON document from the
canonical Kotlin fixture, validates it against the schema the adapter
declares (so the document conforms to the contract its own `schema`
field advertises), and reconciles node/relationship counts and edge
endpoints with the adapter metrics. Writes evidence under
``artifacts/projections-validation/arrows/``.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "python"))
sys.path.insert(0, str(REPO_ROOT / "python" / "tests"))

from conftest import build_kotlin_world  # noqa: E402

from archskillkit.promotion import discover  # noqa: E402
from archskillkit.projections import VisualIntent  # noqa: E402
from archskillkit.projections.adapters.arrows import (  # noqa: E402
    SCHEMA,
    ArrowsAdapter,
)
from archskillkit.projections.schemas import load_schema  # noqa: E402
from archskillkit.projections.writer import project_to_workspace  # noqa: E402


def main() -> int:
    out_root = REPO_ROOT / "artifacts" / "projections-validation" / "arrows"
    out_root.mkdir(parents=True, exist_ok=True)
    artifact = out_root / "kotlin-world.arrows.json"

    with tempfile.TemporaryDirectory(prefix="ark-p7-arrows-") as tmp:
        sandbox = Path(tmp)
        os.environ["XDG_DATA_HOME"] = str(sandbox / "data")
        os.environ["XDG_STATE_HOME"] = str(sandbox / "state")
        repo = sandbox / "kotlin-demo"
        world, index = build_kotlin_world(repo)
        discover(world, index, scan_run_id="scan-1")
        result = project_to_workspace(
            world, ArrowsAdapter(),
            intent=VisualIntent(type="exploration", subject="x"))
        produced = Path(result["path"])
        artifact.write_bytes(produced.read_bytes())
        metrics = {
            "adapter_nodes": result["metrics"]["nodes"],
            "adapter_edges": result["metrics"]["edges"],
        }
        index.close()
        world.close()

    doc = json.loads(artifact.read_text())
    sha256 = hashlib.sha256(artifact.read_bytes()).hexdigest()

    validator = Draft202012Validator(load_schema("arrows-v1"))
    schema_errors = sorted(validator.iter_errors(doc), key=lambda e: e.path)

    parsed_nodes = len(doc.get("nodes", []))
    parsed_relationships = len(doc.get("relationships", []))
    node_ids = {n["id"] for n in doc.get("nodes", [])}
    rels_with_dangling_endpoint = [
        r for r in doc.get("relationships", [])
        if r.get("start") not in node_ids or r.get("end") not in node_ids
    ]
    duplicate_node_ids = [
        n["id"] for n in doc.get("nodes", [])
        if sum(1 for m in doc["nodes"] if m.get("id") == n.get("id")) > 1
    ]

    reconciliation = {
        "adapter_metrics": metrics,
        "declared_schema": doc.get("schema"),
        "parsed_nodes": parsed_nodes,
        "parsed_relationships": parsed_relationships,
        "schema_errors": [
            f"{'/'.join(str(p) for p in err.absolute_path)}: {err.message}"
            for err in schema_errors
        ],
        "rels_with_dangling_endpoint": [
            {"id": r.get("id"), "start": r.get("start"), "end": r.get("end")}
            for r in rels_with_dangling_endpoint
        ],
        "duplicate_node_ids": sorted(set(duplicate_node_ids)),
        "artifact_sha256": sha256,
    }
    (out_root / "reconciliation.json").write_text(
        json.dumps(reconciliation, indent=2, sort_keys=True)
    )

    fail: list[str] = []
    if doc.get("schema") != SCHEMA:
        fail.append(
            f"declared schema mismatch: doc has {doc.get('schema')!r}, "
            f"adapter declares {SCHEMA!r}"
        )
    if schema_errors:
        fail.append(
            f"schema validation: {len(schema_errors)} error(s) — "
            f"see reconciliation.json"
        )
    if parsed_nodes != metrics["adapter_nodes"]:
        fail.append(
            f"node count mismatch: adapter={metrics['adapter_nodes']} "
            f"doc={parsed_nodes}"
        )
    if parsed_relationships != metrics["adapter_edges"]:
        fail.append(
            f"relationship count mismatch: adapter={metrics['adapter_edges']} "
            f"doc={parsed_relationships}"
        )
    if duplicate_node_ids:
        fail.append(
            f"{len(set(duplicate_node_ids))} duplicate node id(s)"
        )
    if rels_with_dangling_endpoint:
        fail.append(
            f"{len(rels_with_dangling_endpoint)} relationship(s) with "
            "dangling start/end"
        )

    summary = out_root / "summary.md"
    lines = [
        "# Arrows adapter — P7 validation evidence",
        "",
        f"- Artifact: `{artifact.relative_to(REPO_ROOT)}`",
        f"- SHA-256: `{sha256}`",
        f"- Adapter metrics: {metrics}",
        f"- Doc parsed: nodes={parsed_nodes}, "
        f"relationships={parsed_relationships}",
        f"- Declared schema: `{doc.get('schema')}`",
        f"- Schema: `arch-skillkit/arrows-v1` (in-tree)",
        "",
        "## Verdict",
        "",
        ("PASS — document conforms to the schema it advertises; "
         "node/relationship counts match adapter metrics; every "
         "relationship points to a real node; node ids are unique."
         if not fail else "FAIL — see reconciliation.json."),
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