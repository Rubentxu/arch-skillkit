"""Simulation application service (V2.5 M2, ADR-0049).

Canonical application-layer implementation of the simulation workflow.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from archskillkit.application.models.simulation import (
    SimulationCommand,
    SimulationResult,
)

if TYPE_CHECKING:
    from archskillkit.world import ArchitectureWorld


class SimulationApplicationService:
    """Application-layer implementation of the counterfactual simulation workflow.

    Implements the simulate use case: applies a counterfactual change to a
    throwaway fork, evaluates the policy gate and fitness drift, and throws
    the fork away. The base world is byte-identical before and after.
    """

    def __init__(
        self,
        world: ArchitectureWorld,
        code_index: "CodeIndex | None" = None,
    ) -> None:
        self._world = world
        self._code_index = code_index

    def simulate(self, cmd: SimulationCommand) -> SimulationResult:
        """Run the counterfactual end-to-end.

        Parameters
        ----------
        cmd
            SimulationCommand describing the verb and parameters.

        Returns
        -------
        SimulationResult
            Counterfactual simulation outcome with policy result and recommendation.
        """
        # Import here to avoid circular dependency at module load time
        from archskillkit.delivery.cli.simulate import run as simulate_run

        verb_args: dict[str, Any] = {}
        if cmd.verb == "relation_add":
            if cmd.source is None or cmd.target is None:
                raise ValueError(
                    f"relation_add requires source and target, got source={cmd.source!r}, target={cmd.target!r}"
                )
            verb_args["source"] = cmd.source
            verb_args["target"] = cmd.target
            verb_args["kind"] = cmd.kind
        elif cmd.verb == "move":
            if cmd.element is None or cmd.to is None:
                raise ValueError(
                    f"move requires element and to, got element={cmd.element!r}, to={cmd.to!r}"
                )
            verb_args["element"] = cmd.element
            verb_args["to"] = cmd.to
        elif cmd.verb == "delete":
            if cmd.element is None:
                raise ValueError(f"delete requires element, got element={cmd.element!r}")
            verb_args["element"] = cmd.element

        result = simulate_run(self._world, cmd.verb, **verb_args)
        return result
