"""Arrows projection adapter (M2-E2, docs/v2/29, ADR-0017).

Renders the Architecture World as an `arch-skillkit/arrows-v1` document
— the same schema the V1 export-arrows pipeline produced — so exploratory
views stay compatible with the existing consumption flow.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from archskillkit import __version__
from archskillkit.projections.contract import (
    ProjectionContext,
    ProjectionMetrics,
    ProjectionResult,
)
from archskillkit.projections.intents import IntentType, VisualIntent

SCHEMA = "arch-skillkit/arrows-v1"


def _sanitize(text: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in text)


class ArrowsAdapter:
    name = "arrows"
    supported_intents = frozenset(
        {"exploration"} & set(IntentType.__args__))  # type: ignore[attr-defined]
    version = "0.2.0"

    def project(self, intent: VisualIntent,
                context: ProjectionContext) -> ProjectionResult:
        artifact = context.annotations.get("artifact")
        if not artifact:
            raise ValueError("arrows adapter requires annotations['artifact']")
        snap = context.snapshot
        elements: list[dict[str, Any]] = sorted(
            snap.get("elements", []), key=lambda e: e["name"])
        relations: list[dict[str, Any]] = sorted(
            snap.get("relations", []),
            key=lambda r: (r["kind"], r["source"], r["target"]))

        ids = {e["name"]: f"n_{_sanitize(e['name']).lower()}" for e in elements}
        used: set[str] = set()
        unique_ids: dict[str, str] = {}
        for name, ident in ids.items():
            candidate, suffix = ident, 2
            while candidate in used:
                candidate = f"{ident}_{suffix}"
                suffix += 1
            used.add(candidate)
            unique_ids[name] = candidate

        document = {
            "schema": SCHEMA,
            "generated_by": f"archskillkit {__version__}",
            "title": f"{snap.get('project_name', 'project')} — architecture",
            "source": {
                "project_id": context.project_id,
                "commit": context.architecture_run,
                "generated_at": "",
                "revision": context.code_index_revision,
            },
            "nodes": [
                {
                    "id": unique_ids[e["name"]],
                    "labels": [e["kind"]],
                    "properties": {
                        "name": e["name"],
                        "origin": e["origin"],
                        "confidence": e["confidence"],
                    },
                }
                for e in elements
            ],
            "relationships": [
                {
                    "id": (f"r_{_sanitize(r['kind']).lower()}_"
                           f"{unique_ids.get(r['source'], 'x')}_"
                           f"{unique_ids.get(r['target'], 'x')}"),
                    "type": r["kind"],
                    "start": unique_ids.get(r["source"], ""),
                    "end": unique_ids.get(r["target"], ""),
                    "properties": {"rule": r.get("rule", ""),
                                   "confidence": r.get("confidence", "high")},
                }
                for r in relations
                if r["source"] in unique_ids and r["target"] in unique_ids
            ],
        }

        path = Path(artifact)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")

        warnings: list[str] = []
        if any(not rel["start"] or not rel["end"]
               for rel in document["relationships"]):
            warnings.append("some relationships lost their endpoints")

        return ProjectionResult(
            format=self.name,
            path=str(path),
            source_snapshot={
                "architecture_run": context.architecture_run,
                "code_index_revision": context.code_index_revision,
            },
            warnings=warnings,
            metrics=ProjectionMetrics(
                nodes=len(document["nodes"]),
                edges=len(document["relationships"]),
            ),
        )
