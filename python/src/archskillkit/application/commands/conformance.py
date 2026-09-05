"""Conformance mining application service (V2.5 M2, ADR-0049).

Canonical application-layer implementation of the conformance mining workflow.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from archskillkit.application.models.conformance import (
    MineConformanceCommand,
    MineConformanceResult,
)

if TYPE_CHECKING:
    from archskillkit.world import ArchitectureWorld


class ConformanceApplicationService:
    """Application-layer implementation of the conformance mining workflow.

    Mines repeated architectural patterns and proposes conformance rule candidates.
    """

    def __init__(self, world: ArchitectureWorld) -> None:
        self._world = world

    def mine_conformance(self, cmd: MineConformanceCommand) -> MineConformanceResult:
        """Mine repeated architectural patterns.

        Parameters
        ----------
        cmd
            MineConformanceCommand with min_support threshold.

        Returns
        -------
        MineConformanceResult
            Mining result with candidate list.
        """
        from archskillkit.conformance_miner import mine

        with self._world:
            candidates = mine(self._world, min_support=cmd.min_support)

        return MineConformanceResult(
            schema="arch-skillkit/conformance-mining-v1",
            project_id=self._world.project_id,
            min_support=cmd.min_support,
            candidates=[c.model_dump() for c in candidates],
        )
