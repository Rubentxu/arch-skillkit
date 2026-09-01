"""Projection writer — domain side of the projection lifecycle
(docs/v2/35): decides WHERE artifacts live, guards manual edits (P6.3),
records metadata sidecars and computes the source revision hash used for
staleness detection (P6.1). Adapters decide HOW to render and write the
artifact at the path given in the context annotations.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from archskillkit.projections import (
    ProjectionAdapter,
    ProjectionContext,
    ProjectionMetadata,
    VisualIntent,
)
from archskillkit.world import ArchitectureWorld

ARTIFACT_PATHS = {
    "likec4": "likec4/model.c4",
    "arrows": "arrows/architecture.arrows",
}

PREFERRED_INTENT = {
    "likec4": "architecture",
    "arrows": "exploration",
}


class ProjectionError(Exception):
    """A projection lifecycle rule was violated."""


def revision_hash(snapshot: dict) -> str:
    """Stable content hash of the projected world (source revision)."""
    payload = {"objects": snapshot.get("objects", {}),
               "relations": snapshot.get("relations", [])}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def _named_snapshot(world: ArchitectureWorld) -> dict[str, Any]:
    """Snapshot flattened to named elements/relations for rendering."""
    objects = world.snapshot()
    names = {oid: obj["data"].get("name", oid)
             for oid, obj in objects["objects"].items()
             if obj["type"] == "architecture_element"}
    elements = [
        {"name": obj["data"]["name"],
         "kind": obj["data"]["kind"],
         "origin": obj["data"]["origin"],
         "confidence": obj["data"]["confidence"]}
        for obj in objects["objects"].values()
        if obj["type"] == "architecture_element"
    ]
    relations = [
        {"kind": r["type"],
         "source": names.get(r["source"], r["source"]),
         "target": names.get(r["target"], r["target"]),
         "rule": (r["data"] or {}).get("rule", ""),
         "confidence": (r["data"] or {}).get("confidence", "high")}
        for r in objects["relations"]
        if r["source"] in names and r["target"] in names
    ]
    return {"project_name": world.project_name,
            "elements": elements, "relations": relations}


def project_to_workspace(world: ArchitectureWorld, adapter: ProjectionAdapter,
                         force: bool = False,
                         intent: VisualIntent | None = None) -> dict:
    """Project the current world through `adapter` into the workspace.

    Writes the artifact (via the adapter) plus a metadata sidecar.
    Raises ProjectionError when the existing artifact was manually
    modified and `force` is not set (UAT-P12).
    """
    rel_path = ARTIFACT_PATHS.get(adapter.name)
    if rel_path is None:
        raise ProjectionError(f"no workspace path for format '{adapter.name}'")
    artifact = world.workspace / rel_path
    meta_path = artifact.with_name(artifact.name + ".meta.json")

    snapshot_dict = world.snapshot()
    revision = revision_hash(snapshot_dict)

    if artifact.exists() and meta_path.exists():
        old = json.loads(meta_path.read_text())
        # Manual-edit detection is content-based (ADR-0030, UAT-P12): if
        # the artifact on disk no longer matches what this generator last
        # wrote, a hand edit happened — refuse to overwrite without force.
        old_hash = old.get("generated_sha256")
        hand_edited = (
            (old_hash is not None
             and hashlib.sha256(artifact.read_bytes()).hexdigest() != old_hash)
            or bool(old.get("manually_modified"))
        )
        if hand_edited and not force:
            raise ProjectionError(
                f"{rel_path} was manually modified; regenerate with force "
                "or keep it as a new revision")

    intent = intent or VisualIntent(
        type=PREFERRED_INTENT.get(adapter.name, "exploration"),
        subject=world.project_name)
    context = ProjectionContext(
        project_id=world.project_id,
        architecture_run=world.run_id,
        code_index_revision=revision,
        snapshot=_named_snapshot(world),
        annotations={"artifact": str(artifact)},
    )
    result = adapter.project(intent, context)

    meta = ProjectionMetadata(
        projection_id=f"{world.project_id}-{adapter.name}",
        projection_type=adapter.name,
        visual_intent=intent.type,
        source={
            "project_id": world.project_id,
            "architecture_run": world.run_id,
            "code_index_revision": revision,
        },
        adapter_version=adapter.version,
        status="generated",
        artifact_path=rel_path,
        generated_sha256=(
            hashlib.sha256(artifact.read_bytes()).hexdigest()
            if artifact.exists() else None),
    )
    meta_path.write_text(meta.model_dump_json(indent=2) + "\n")
    return {
        "format": adapter.name,
        "path": str(artifact),
        "metrics": result.metrics.model_dump(),
        "warnings": result.warnings,
        "stale": False,
        "revision": revision,
    }


def load_metadata(world: ArchitectureWorld, fmt: str) -> dict | None:
    rel_path = ARTIFACT_PATHS.get(fmt)
    if rel_path is None:
        return None
    meta_path = world.workspace / (rel_path + ".meta.json")
    if not meta_path.exists():
        return None
    return json.loads(meta_path.read_text())


def is_stale(world: ArchitectureWorld, fmt: str) -> bool:
    """A projection is stale when the world content changed after it was
    generated (docs/v2/35: source snapshot changes → stale)."""
    meta = load_metadata(world, fmt)
    if meta is None:
        return False
    current = revision_hash(world.snapshot())
    return current != meta["source"]["code_index_revision"]
