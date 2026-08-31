"""V2.2 projection layer — VisualIntent, adapter contract, metadata, router.

The domain never imports visualization applications (UAT-P18): adapters
are registered by the caller; this package only knows the contract.
"""

from archskillkit.projections.contract import (
    ProjectionAdapter,
    ProjectionContext,
    ProjectionMetrics,
    ProjectionResult,
)
from archskillkit.projections.intents import IntentType, VisualIntent
from archskillkit.projections.metadata import ProjectionMetadata, ProjectionStatus
from archskillkit.projections.router import ProjectionRouter

__all__ = [
    "IntentType",
    "ProjectionAdapter",
    "ProjectionContext",
    "ProjectionMetadata",
    "ProjectionMetrics",
    "ProjectionResult",
    "ProjectionRouter",
    "ProjectionStatus",
    "VisualIntent",
]
