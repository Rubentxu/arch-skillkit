"""Build an ArchitectureSnapshot from live world/index/git state.

Revisions only — the graph is never copied (ADR-0033). Everything here
is deterministic for the same (event log, code generation, git state):
no timestamps, no wall clock, no environment probes beyond the analyzed
repository itself.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from archskillkit.application.models.snapshot import (
    ArchitectureSnapshot,
    CodeRevision,
    KnowledgeSummary,
    ProjectRevision,
    WorldRevision,
)

_EMPTY_REVISION = "none"


def _git(root: str | Path, *args: str) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True, text=True, check=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout


def _git_commit(root: str | Path) -> str:
    return (_git(root, "rev-parse", "HEAD") or "").strip() or "unknown"


def _dirty_digest(root: str | Path) -> str | None:
    """sha256 over `git status --porcelain`; None means clean tree."""
    porcelain = _git(root, "status", "--porcelain")
    if not porcelain:
        return None
    return hashlib.sha256(porcelain.encode("utf-8")).hexdigest()


def _world_revision(world) -> WorldRevision:
    events = world.graph.events
    event_id = events[-1].id if events else "evt_000"
    projection = world.snapshot()
    digest = hashlib.sha256(
        json.dumps(projection, sort_keys=True).encode("utf-8")).hexdigest()
    return WorldRevision(event_id=event_id, digest=digest)


def _policy_revision(world) -> str:
    """Digest over the declared architecture rules (ADR-0022)."""
    rules = world.find_objects("architecture_rule")
    if not rules:
        return _EMPTY_REVISION
    payload = sorted(
        (r["data"].get("name", ""), r["data"].get("statement", ""),
         r["data"].get("forbidden_relation", ""),
         r["data"].get("source_category", ""),
         r["data"].get("target_category", ""),
         r["data"].get("severity", ""))
        for r in rules
    )
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _sensor_revisions(world) -> list[str]:
    """`tool@revision` pairs from the latest recorded scan run, if any."""
    runs = world.find_objects("scan_run")
    if not runs:
        return []
    latest = max(runs, key=lambda r: r["id"])
    tools = latest["data"].get("tools") or {}
    return sorted(f"{name}@{rev}" for name, rev in tools.items())


def build_snapshot(world, code_index=None,
                   artifact_manifest_digest: str | None = None,
                   ) -> ArchitectureSnapshot:
    """Gather revisions from an open world (+ optional CodeIndex) into a
    finalized snapshot. The world must be open."""
    projection = world.snapshot()
    counts = projection.get("counts", {})
    knowledge = KnowledgeSummary(
        elements=counts.get("architecture_element", 0),
        relations=len(projection.get("relations", [])),
    )
    generation = _EMPTY_REVISION
    if code_index is not None:
        generation = code_index.current_generation or _EMPTY_REVISION
    snapshot = ArchitectureSnapshot(
        project_revision=ProjectRevision(
            git_commit=_git_commit(world.root),
            dirty_digest=_dirty_digest(world.root),
        ),
        code_revision=CodeRevision(
            generation=generation,
            sensor_revisions=_sensor_revisions(world),
        ),
        world_revision=_world_revision(world),
        policy_revision=_policy_revision(world),
        knowledge=knowledge,
        artifact_manifest_digest=artifact_manifest_digest,
    )
    return snapshot.with_snapshot_id()
