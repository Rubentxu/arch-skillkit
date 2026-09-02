"""GetStatus use case (docs/v2/55 §2, §5).

Status is a projection of revisions plus *typed action suggestions* —
never shell strings. Suggestion rules are deterministic: the same world
state always yields the same suggestions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict

from archskillkit.application.models.actions import ActionSuggestion
from archskillkit.application.models.snapshot import ArchitectureSnapshot
from archskillkit.application.snapshot_builder import build_snapshot

if TYPE_CHECKING:
    from archskillkit.application.ports.architecture_query import (
        ArchitectureQueryPort,
    )

STATUS_SCHEMA = "arch-skillkit/status-result-v1"

_EMPTY = "none"


class StatusResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema: Literal["arch-skillkit/status-result-v1"] = STATUS_SCHEMA  # type: ignore[assignment]
    project_id: str
    project_name: str
    root: str
    snapshot: ArchitectureSnapshot
    suggestions: list[ActionSuggestion]


def _suggest(action_id: str, reason_code: str) -> ActionSuggestion:
    return ActionSuggestion(
        action_id=action_id,
        reason_code=reason_code,
        mutation_scope="workspace",
        risk="low",
        preconditions=["project_initialized"],
        expected_effects=["scan repository and refresh the architecture"],
    )


def _suggestions(world: ArchitectureQueryPort,
                 snapshot: ArchitectureSnapshot,
                 ) -> list[ActionSuggestion]:
    """Deterministic rules; doc/v2/55 §5 is the INDEX_STALE contract."""
    out: list[ActionSuggestion] = []
    if snapshot.code_revision.generation == _EMPTY:
        out.append(_suggest("discover", "INDEX_MISSING"))
    elif snapshot.project_revision.dirty_digest is not None:
        out.append(_suggest("discover", "INDEX_STALE"))
    if not world.find_objects("architecture_element"):
        out.append(_suggest("discover", "WORLD_EMPTY"))
    return out


def get_status(world: ArchitectureQueryPort,
               code_index=None) -> StatusResult:
    """Project status: identity, snapshot and typed next actions."""
    snapshot = build_snapshot(world, code_index)
    return StatusResult(
        project_id=world.project_id,
        project_name=world.project_name,
        root=world.root,
        snapshot=snapshot,
        suggestions=_suggestions(world, snapshot),
    )
