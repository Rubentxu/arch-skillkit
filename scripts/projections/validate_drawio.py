#!/usr/bin/env python3
r"""draw.io projection adapter validation (docs/v2/47 P7).

Generates the mxfile (mxGraph XML) artifact from the canonical Kotlin
fixture, round-trips it through lxml (the same XML stack draw.io uses
to parse), reconciles cell counts and source/target references with
the adapter metrics, and optionally converts the artifact to PNG via
``drawio-batch`` if it is available (skipped otherwise — visual evidence
is documented as a follow-up manual step).

Writes evidence under ``artifacts/projections-validation/drawio/``.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from lxml import etree

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "python"))
sys.path.insert(0, str(REPO_ROOT / "python" / "tests"))

from conftest import build_kotlin_world  # noqa: E402

from archskillkit.promotion import discover  # noqa: E402
from archskillkit.projections import VisualIntent  # noqa: E402
from archskillkit.projections.adapters.drawio import DrawioAdapter  # noqa: E402
from archskillkit.projections.writer import project_to_workspace  # noqa: E402


def parse_mxfile(path: Path) -> dict:
    tree = etree.parse(str(path))
    root = tree.getroot()
    if root.tag != "mxfile":
        raise ValueError(f"expected root <mxfile>, got <{root.tag}>")
    cells = root.findall(".//mxCell")
    vertices = [c for c in cells if c.get("vertex") == "1"]
    edges = [c for c in cells if c.get("edge") == "1"]
    node_ids = {c.get("id") for c in vertices}
    dangling = [
        c.get("id") for c in edges
        if c.get("source") not in node_ids or c.get("target") not in node_ids
    ]
    return {
        "root_tag": root.tag,
        "cells_total": len(cells),
        "vertices": len(vertices),
        "edges": len(edges),
        "node_ids": sorted(node_ids),
        "edges_without_label": [
            c.get("id") for c in edges if not c.get("value")
        ],
        "edges_with_dangling_endpoint": dangling,
    }


def main() -> int:
    out_root = REPO_ROOT / "artifacts" / "projections-validation" / "drawio"
    out_root.mkdir(parents=True, exist_ok=True)
    artifact = out_root / "kotlin-world.drawio"

    with tempfile.TemporaryDirectory(prefix="ark-p7-drawio-") as tmp:
        sandbox = Path(tmp)
        os.environ["XDG_DATA_HOME"] = str(sandbox / "data")
        os.environ["XDG_STATE_HOME"] = str(sandbox / "state")
        repo = sandbox / "kotlin-demo"
        world, index = build_kotlin_world(repo)
        discover(world, index, scan_run_id="scan-1")
        result = project_to_workspace(
            world, DrawioAdapter(),
            intent=VisualIntent(type="technical_diagram", subject="x"))
        produced = Path(result["path"])
        artifact.write_bytes(produced.read_bytes())
        metrics = {
            "adapter_nodes": result["metrics"]["nodes"],
            "adapter_edges": result["metrics"]["edges"],
        }
        index.close()
        world.close()

    sha256 = hashlib.sha256(artifact.read_bytes()).hexdigest()
    parsed = parse_mxfile(artifact)

    visual_png: str | None = None
    drawio_batch = shutil.which("drawio-batch")
    if drawio_batch:
        png = out_root / "kotlin-world.png"
        try:
            subprocess.run(
                [drawio_batch, str(artifact), "--format", "png",
                 "--output", str(png)],
                check=True, capture_output=True, timeout=120,
            )
            visual_png = str(png.relative_to(REPO_ROOT))
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            visual_png = f"FAILED: {exc}"
    else:
        visual_png = "skipped (drawio-batch not installed)"

    reconciliation = {
        "adapter_metrics": metrics,
        "parsed": parsed,
        "artifact_sha256": sha256,
        "visual_png": visual_png,
    }
    (out_root / "reconciliation.json").write_text(
        json.dumps(reconciliation, indent=2, sort_keys=True)
    )

    fail: list[str] = []
    if parsed["root_tag"] != "mxfile":
        fail.append(f"root tag not mxfile: got <{parsed['root_tag']}>")
    if parsed["vertices"] != metrics["adapter_nodes"]:
        fail.append(
            f"vertex count mismatch: adapter={metrics['adapter_nodes']} "
            f"mxfile={parsed['vertices']}"
        )
    if parsed["edges"] != metrics["adapter_edges"]:
        fail.append(
            f"edge count mismatch: adapter={metrics['adapter_edges']} "
            f"mxfile={parsed['edges']}"
        )
    if parsed["edges_with_dangling_endpoint"]:
        fail.append(
            f"{len(parsed['edges_with_dangling_endpoint'])} edge(s) with "
            "dangling source/target"
        )
    if parsed["edges_without_label"]:
        fail.append(
            f"{len(parsed['edges_without_label'])} edge(s) without label"
        )

    summary = out_root / "summary.md"
    lines = [
        "# draw.io adapter — P7 validation evidence",
        "",
        f"- Artifact: `{artifact.relative_to(REPO_ROOT)}`",
        f"- SHA-256: `{sha256}`",
        f"- Adapter metrics: {metrics}",
        f"- mxfile parsed: cells={parsed['cells_total']}, "
        f"vertices={parsed['vertices']}, edges={parsed['edges']}",
        "",
        "## Visual evidence",
        "",
    ]
    if visual_png and visual_png.startswith("artifacts/"):
        lines.append(f"- PNG render: `{visual_png}` (via drawio-batch)")
    elif visual_png and visual_png.startswith("FAILED"):
        lines.append(f"- PNG render: FAILED — {visual_png}")
    else:
        lines.append(
            "- PNG render: skipped (drawio-batch not installed). "
            "Manual capture with `draw.io <file>` is the documented "
            "follow-up step (docs/v2/47). Layout review by a human is "
            "deferred until the captured PNG is available."
        )
    lines += [
        "",
        "## Verdict",
        "",
        ("PASS — mxfile/mxGraph XML is well-formed; vertex/edge counts "
         "match adapter metrics; every edge has a label and points to a "
         "real vertex." if not fail else "FAIL — see reconciliation.json."),
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