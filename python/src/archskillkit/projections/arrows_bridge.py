"""Arrows bridge shape mapper (V2.4 M5 slice 26).

Maps the arch-skillkit/arrows-v1 artifact (produced by
archskillkit.projections.adapters.arrows.ArrowsAdapter) to the
bridge postMessage graph shape expected by the Arrows.app embed
protocol (src/embed/bridge/bridge.ts):

Bridge graph shape:
  nodes: [{id, caption, position:{x,y}, labels, properties, style}]
  rels:  [{id, fromId, toId, type, properties, style}]

Arrows artifact shape (arrows-v1):
  nodes: [{id, labels, properties}]   # properties.name → caption
  rels:  [{id, type, start, end, properties}]  # start/end → node ids
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

# Bridge graph schema
BRIDGE_SCHEMA = "arch-skillkit/arrows-artifact-v1"

# Deterministic grid: deterministic positions so successive projections
# of the same world produce the same artifact SHA (stable base_drift).
_GRID_COLS = 4
_GRID_CELL_W = 240
_GRID_CELL_H = 120


def _grid_position(idx: int) -> dict[str, float]:
    """Deterministic grid position for node index `idx`."""
    col = idx % _GRID_COLS
    row = idx // _GRID_COLS
    return {"x": float(col * _GRID_CELL_W), "y": float(row * _GRID_CELL_H)}


def arrows_to_bridge(arrows_doc: dict[str, Any]) -> dict[str, Any]:
    """Map an arrows-v1 document to the bridge graph shape.

    Pure function — deterministic, unit-testable.

    Shape rules (spike 25b, PASS):
    - name property → caption
    - start/end → fromId/toId
    - synthesised deterministic grid positions (stable across projections)
    - labels[0] from the element kind
    - style left at defaults (Arrows handles theming)
    """
    nodes_out: list[dict[str, Any]] = []
    rels_out: list[dict[str, Any]] = []

    # Index nodes by id for rel resolution
    node_ids: set[str] = set()

    for idx, node in enumerate(arrows_doc.get("nodes", [])):
        nid = str(node["id"])
        node_ids.add(nid)
        caption = node.get("properties", {}).get("name", nid)
        labels = node.get("labels", [])
        pos = _grid_position(idx)

        nodes_out.append(
            {
                "id": nid,
                "caption": caption,
                "position": pos,
                "labels": labels,
                "properties": {
                    k: v
                    for k, v in node.get("properties", {}).items()
                    if k != "name"  # name is the caption
                },
                "style": None,
            }
        )

    for rel in arrows_doc.get("relationships", []):
        from_id = str(rel.get("start", ""))
        to_id = str(rel.get("end", ""))
        # Only emit rels where both endpoints resolve
        if from_id not in node_ids or to_id not in node_ids:
            continue
        rels_out.append(
            {
                "id": str(rel["id"]),
                "fromId": from_id,
                "toId": to_id,
                "type": rel.get("type", ""),
                "properties": rel.get("properties", {}),
                "style": None,
            }
        )

    return {"nodes": nodes_out, "rels": rels_out}


def compute_sha256(doc: dict[str, Any]) -> str:
    """SHA-256 of the serialised arrows document.

    Uses the same serialization parameters as the arrows adapter:
    indent=2, sort_keys=True, trailing newline — so the result matches
    the artifact bytes that were written to disk and the SHA stored in
    metadata.
    """
    return hashlib.sha256((json.dumps(doc, indent=2, sort_keys=True) + "\n").encode()).hexdigest()


def build_envelope(
    arrows_doc: dict[str, Any],
    generated_sha256: str | None = None,
) -> dict[str, Any]:
    """Build the full /arrows-artifact response envelope.

    Args:
        arrows_doc: parsed arrows-v1 document
        generated_sha256: SHA-256 recorded at generation time (from metadata
            sidecar). None when metadata is absent (e.g. pre-lifecycle worlds).

    Returns:
        arch-skillkit/arrows-artifact-v1 envelope dict.
    """
    graph = arrows_to_bridge(arrows_doc)
    current_sha = compute_sha256(arrows_doc)
    return {
        "schema": BRIDGE_SCHEMA,
        "graph": graph,
        "docVersion": 1,
        "sha256": current_sha,
        "generated_sha256": generated_sha256,
        "base_drift": (bool(generated_sha256) and generated_sha256 != current_sha),
    }
