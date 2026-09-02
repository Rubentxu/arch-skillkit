"""Multi-format renderers for the gate result (V2.4 M3, docs/v2/58).

One GateResult, three surfaces:
- JSON: canonical, schema-bound (arch-skillkit/gate-result-v1)
- Markdown: human-readable summary, deterministic, one row per dimension
- SARIF 2.1.0: ingestable by GitHub code-scanning, severity mapped
  from the dimension status

All three renderers are pure functions: same input -> byte-identical
output. They never touch the world.
"""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from archskillkit.application.queries.fitness import GateResult

ReportFormat = Literal["json", "markdown", "sarif"]


def render_json(result: GateResult) -> str:
    return json.dumps(result.model_dump(), indent=2) + "\n"


# ---- markdown ---------------------------------------------------------------


def _status_emoji(status: str) -> str:
    return {"pass": "PASS", "warn": "WARN", "fail": "FAIL",
            "na": "N/A"}.get(status, status.upper())


def render_markdown(result: GateResult, *, project: str = "") -> str:
    lines: list[str] = []
    verdict = "PASS" if result.verdict == "pass" else "FAIL"
    lines.append(f"# Architecture fitness gate — {verdict}")
    if project:
        lines.append(f"\nProject: `{project}`")
    lines.append(f"\nSnapshot: `{result.snapshot_id}`\n")
    lines.append("| Dimension | Status | Value | Evidence |")
    lines.append("|-----------|--------|-------|----------|")
    for name in sorted(result.dimensions):
        d = result.dimensions[name]
        value = "" if d.value is None else str(d.value)
        evidence = ", ".join(d.evidence_refs) or "—"
        lines.append(f"| {name} | {_status_emoji(d.status)} | {value}"
                     f" | {evidence} |")
    if result.waived:
        lines.append("\n## Active waivers")
        for w in result.waived:
            lines.append(f"- {w['dimension']} (waiver {w['waiver_id']}, "
                         f"expires {w['expires_at']})")
    if result.expired_waivers:
        lines.append("\n## Expired waivers (do NOT excuse the gate)")
        for w in result.expired_waivers:
            lines.append(f"- {w['dimension']} (waiver {w['waiver_id']}, "
                         f"expired {w['expires_at']})")
    if result.failed_dimensions:
        lines.append("\n## Failed dimensions")
        for name in result.failed_dimensions:
            lines.append(f"- {name}")
    return "\n".join(lines) + "\n"


# ---- SARIF 2.1.0 ------------------------------------------------------------


_SEVERITY = {"pass": "none", "warn": "warning",
             "fail": "error", "na": "none"}


def render_sarif(result: GateResult, *, project: str = "",
                 tool_version: str = "arch-skillkit/0.0.0") -> dict:
    rules: dict[str, dict] = {}
    results: list[dict] = []
    for name, d in result.dimensions.items():
        rules[name] = {
            "id": f"arch-skillkit/{name}",
            "name": name,
            "shortDescription": {"text": f"Architecture fitness: {name}"},
            "defaultConfiguration": {
                "level": _SEVERITY.get(d.status, "none")},
        }
        if d.status in ("pass", "na"):
            continue
        digest = hashlib.sha256(f"{name}:{d.status}".encode()).hexdigest()
        results.append({
            "ruleId": f"arch-skillkit/{name}",
            "level": _SEVERITY[d.status],
            "message": {"text": f"{name}={d.value} ({d.status})"},
            "locations": [{
                "physicalLocation": {
                    "artifactLocation": {"uri": project or ".",
                                         "uriBaseId": "%SRCROOT%"},
                },
                "logicalLocation": {
                    "name": result.snapshot_id,
                    "kind": "snapshot",
                },
            }],
            "partialFingerprints": {"architectureFitness": digest},
        })
    return {
        "$schema": (
            "https://json.schemastore.org/sarif-2.1.0.json"),
        "version": "2.1.0",
        "runs": [{
            "tool": {
                "driver": {
                    "name": "arch-skillkit-gate",
                    "version": tool_version,
                    "rules": list(rules.values()),
                },
            },
            "results": results,
        }],
    }
