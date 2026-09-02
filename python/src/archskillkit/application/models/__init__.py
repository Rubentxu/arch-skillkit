"""Application DTOs (V2.4). Schemas: design/schemas/v2.4/*.yaml."""

import warnings

# The wire name `schema` is contractual (docs/v2/55 §4: every
# machine-readable output carries a stable schema id). Pydantic v2
# emits a UserWarning because v1's BaseModel.schema() shadowed the
# name; the field is intentional and the JSON contract wins. Filtered
# here, before any model class is defined, so CLI output stays clean
# (bats seam tests parse combined stdout/stderr).
warnings.filterwarnings(
    "ignore", message=r'.*Field name "schema".*', category=UserWarning)

from archskillkit.application.models.actions import (
    ActionSuggestion,
    MutationScope,
    Risk,
)
from archskillkit.application.models.snapshot import (
    SNAPSHOT_SCHEMA,
    ArchitectureSnapshot,
    CodeRevision,
    KnowledgeSummary,
    ProjectRevision,
    WorldRevision,
    snapshot_digest,
)

__all__ = [
    "SNAPSHOT_SCHEMA",
    "ActionSuggestion",
    "ArchitectureSnapshot",
    "CodeRevision",
    "KnowledgeSummary",
    "MutationScope",
    "ProjectRevision",
    "Risk",
    "WorldRevision",
    "snapshot_digest",
]
