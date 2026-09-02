#!/usr/bin/env python3
"""LikeC4 projection adapter validation (docs/v2/47 P7).

Generates the LikeC4 `.c4` model from the canonical Kotlin fixture,
runs ``likec4 export --dry-run`` to exercise the likec4 language
services (validation + model build) without requiring a headless
browser for the PNG render, and reconciles element/relation counts
with the adapter metrics. If Chrome is available the render runs and
captures a PNG; otherwise the visual capture is documented as a
follow-up step.

Writes evidence under ``artifacts/projections-validation/likec4/``.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "python"))
sys.path.insert(0, str(REPO_ROOT / "python" / "tests"))

from conftest import build_kotlin_world  # noqa: E402

from archskillkit.promotion import discover  # noqa: E402
from archskillkit.projections import VisualIntent  # noqa: E402
from archskillkit.projections.adapters.likec4 import LikeC4Adapter  # noqa: E402
from archskillkit.projections.writer import project_to_workspace  # noqa: E402


def count_elements_relations(text: str) -> tuple[int, int]:
    """Crude parse of the LikeC4 DSL emitted by the adapter.

    Counts nested ``<id> = <kind> 'name'`` blocks (elements) and
    top-level ``target.<id> -> target.<id> 'kind'`` arrows
    (relations). The adapter emits internals inside ``target`` with
    identifiers ``n<digits>`` and externals at the model root with
    identifiers ``x<digits>``. Relations are always top-level. Good
    enough for a sanity reconciliation against the adapter metrics;
    the authoritative count is the one likec4 reports when it builds
    the model.
    """
    elements = 0
    relations = 0
    in_target = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue
        if stripped.startswith("model"):
            in_target = False  # reset at model boundary
            continue
        if stripped.startswith("target = system"):
            in_target = True
            continue
        # Element declarations: inside target we have internals n<id>,
        # outside we have externals x<id>. Both follow the same shape:
        # `<id> = <kind> '<name>' {`.
        if re.match(r"^[xn]\d+\s*=\s*\w+\s*'", stripped):
            elements += 1
            continue
        # Relations are always top-level `target.<id> -> target.<id> '<kind>' {`.
        if re.match(r"^target\.[xn]\d+\s*->", stripped):
            relations += 1
        # Unused but tracked for clarity.
        _ = in_target
    return elements, relations


def main() -> int:
    out_root = REPO_ROOT / "artifacts" / "projections-validation" / "likec4"
    out_root.mkdir(parents=True, exist_ok=True)
    artifact = out_root / "kotlin-world.c4"

    with tempfile.TemporaryDirectory(prefix="ark-p7-likec4-") as tmp:
        sandbox = Path(tmp)
        os.environ["XDG_DATA_HOME"] = str(sandbox / "data")
        os.environ["XDG_STATE_HOME"] = str(sandbox / "state")
        repo = sandbox / "kotlin-demo"
        world, index = build_kotlin_world(repo)
        discover(world, index, scan_run_id="scan-1")
        result = project_to_workspace(
            world, LikeC4Adapter(),
            intent=VisualIntent(type="architecture", subject="x"))
        produced = Path(result["path"])
        artifact.write_bytes(produced.read_text().encode("utf-8"))
        metrics = {
            "adapter_nodes": result["metrics"]["nodes"],
            "adapter_edges": result["metrics"]["edges"],
        }
        index.close()
        world.close()

    text = artifact.read_text()
    sha256 = hashlib.sha256(artifact.read_bytes()).hexdigest()
    parsed_elements, parsed_relations = count_elements_relations(text)

    likec4 = shutil.which("likec4")
    cli_rc: int | None = None
    cli_stdout = ""
    cli_stderr = ""
    if likec4:
        with tempfile.TemporaryDirectory(prefix="ark-p7-likec4-cli-") as tmp:
            ws = Path(tmp) / "workspace"
            (ws / "src").mkdir(parents=True)
            (ws / "src" / "model.c4").write_text(text)
            out = Path(tmp) / "out"
            out.mkdir()
            try:
                cp = subprocess.run(
                    [likec4, "export", "--dry-run", "-o", str(out), str(ws)],
                    capture_output=True, text=True, timeout=120,
                )
                cli_rc = cp.returncode
                cli_stdout = cp.stdout
                cli_stderr = cp.stderr
            except subprocess.TimeoutExpired as exc:
                cli_rc = -1
                cli_stderr = f"timeout: {exc}"

    cli_clean = bool(
        cli_rc == 0 and "Done" in cli_stdout and "Failed" not in cli_stdout
    )

    png: str | None = None
    if likec4 and cli_clean:
        with tempfile.TemporaryDirectory(prefix="ark-p7-likec4-png-") as tmp:
            ws = Path(tmp) / "workspace"
            (ws / "src").mkdir(parents=True)
            (ws / "src" / "model.c4").write_text(text)
            out = Path(tmp) / "out"
            out.mkdir()
            try:
                cp = subprocess.run(
                    [likec4, "export", "-o", str(out), str(ws)],
                    capture_output=True, text=True, timeout=240,
                )
                if cp.returncode == 0:
                    produced_png = next(out.rglob("*.png"), None)
                    if produced_png:
                        target = out_root / "kotlin-world-index.png"
                        target.write_bytes(produced_png.read_bytes())
                        png = str(target.relative_to(REPO_ROOT))
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                png = "FAILED: headless render unavailable (likely missing Chrome)"

    if png is None and not cli_clean:
        png = "skipped (likec4 export --dry-run failed — see cli_stderr)"
    elif png is None:
        png = "skipped (likec4 export succeeded but PNG not produced)"

    reconciliation = {
        "adapter_metrics": metrics,
        "parsed_elements": parsed_elements,
        "parsed_relations": parsed_relations,
        "likec4_cli_rc": cli_rc,
        "likec4_cli_clean": cli_clean,
        "artifact_sha256": sha256,
        "visual_png": png,
    }
    if cli_stderr:
        reconciliation["likec4_cli_stderr_tail"] = cli_stderr[-400:]
    (out_root / "reconciliation.json").write_text(
        json.dumps(reconciliation, indent=2, sort_keys=True)
    )

    fail: list[str] = []
    if parsed_elements != metrics["adapter_nodes"]:
        fail.append(
            f"element count mismatch: adapter={metrics['adapter_nodes']} "
            f"dsl={parsed_elements}"
        )
    if parsed_relations != metrics["adapter_edges"]:
        fail.append(
            f"relation count mismatch: adapter={metrics['adapter_edges']} "
            f"dsl={parsed_relations}"
        )
    if not likec4:
        fail.append("likec4 CLI not installed; cannot validate model build")
    elif not cli_clean:
        fail.append(
            f"likec4 export --dry-run failed (rc={cli_rc}); see reconciliation.json"
        )

    summary = out_root / "summary.md"
    lines = [
        "# LikeC4 adapter — P7 validation evidence",
        "",
        f"- Artifact: `{artifact.relative_to(REPO_ROOT)}`",
        f"- SHA-256: `{sha256}`",
        f"- Adapter metrics: {metrics}",
        f"- DSL parsed: elements={parsed_elements}, relations={parsed_relations}",
        f"- likec4 CLI: {likec4 or 'NOT INSTALLED'}",
        "",
        "## likec4 export --dry-run",
        "",
    ]
    if cli_clean:
        lines.append("- ✅ likec4 validated the model and built it without errors")
    elif likec4:
        lines.append(
            f"- ❌ likec4 export --dry-run failed (rc={cli_rc}). "
            "Model build rejected the generated DSL — see "
            "reconciliation.json for stderr tail."
        )
    else:
        lines.append("- ⏭️  likec4 CLI missing — install with "
                    "`npm i -g @likec4/cli` to enable this check.")
    lines += [
        "",
        "## Visual evidence",
        "",
    ]
    if png and png.startswith("artifacts/"):
        lines.append(f"- PNG render: `{png}`")
    elif png and png.startswith("FAILED"):
        lines.append(f"- PNG render: FAILED — {png}")
    else:
        lines.append(f"- PNG render: {png}")
    lines += [
        "",
        "## Verdict",
        "",
        ("PASS — adapter counts match the DSL emitted; likec4 builds "
         "the model without errors; relationships reference real nodes "
         "via FQN."
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