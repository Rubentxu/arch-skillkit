"""Projection Router — deterministic intent → format routing.

Preference table follows docs/v2/26-visual-intent-spec.md ("Tipos
iniciales" destination preferences). Size thresholds (docs/v2/34) refine
the ambiguity cases in Phase P5; routing stays deterministic now.
"""

from __future__ import annotations

from typing import Iterable

from archskillkit.projections.intents import IntentType, VisualIntent
from archskillkit.projections.contract import ProjectionAdapter

# Deterministic preference per intent type. Where the spec allows two
# destinations (proposal_board, investigation), the first listed format
# wins until Phase P5 thresholds refine the choice.
PREFERENCE: dict[IntentType, str] = {
    "architecture": "likec4",
    "exploration": "arrows",
    "technical_diagram": "drawio",
    "knowledge_map": "jsoncanvas",
    "dependency_graph": "graphml",
    "large_graph_analysis": "graphml",
    "proposal_board": "jsoncanvas",
    "investigation": "jsoncanvas",
}


class ProjectionRouter:
    class RoutingError(Exception):
        """No adapter can serve the requested intent."""

    def __init__(self, adapters: Iterable[ProjectionAdapter]):
        self._by_format: dict[str, ProjectionAdapter] = {}
        for adapter in adapters:
            if adapter.name in self._by_format:
                raise self.RoutingError(f"duplicate adapter for format: {adapter.name}")
            self._by_format[adapter.name] = adapter

    def route(
        self, intent: VisualIntent, force: str | None = None
    ) -> ProjectionAdapter:
        """Pick the adapter for this intent; `force` is the user override
        (docs/v2/39 UAT-P11) and must name a registered, intent-compatible
        format."""
        target = force if force is not None else PREFERENCE[intent.type]
        adapter = self._by_format.get(target)
        if adapter is None:
            raise self.RoutingError(
                f"no adapter registered for format '{target}' "
                f"(intent: {intent.type})")
        if intent.type not in adapter.supported_intents:
            raise self.RoutingError(
                f"adapter '{target}' does not support intent '{intent.type}'")
        return adapter
