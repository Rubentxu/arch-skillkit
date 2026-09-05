"""Tests for SimulationApplicationService (V2.5 M2).

Tests the simulate use case through the application layer.
"""

from __future__ import annotations

import pytest

from archskillkit.application.commands.simulation import SimulationApplicationService
from archskillkit.application.models.simulation import SimulationCommand


class TestSimulationApplicationService:
    """Happy-path tests for SimulationApplicationService."""

    def test_simulation_command_model(self):
        """SimulationCommand can be constructed with all verb variants."""
        # relation_add
        cmd = SimulationCommand(
            verb="relation_add",
            source="src",
            target="dst",
            kind="depends_on",
        )
        assert cmd.verb == "relation_add"
        assert cmd.source == "src"
        assert cmd.target == "dst"
        assert cmd.kind == "depends_on"

        # move
        cmd = SimulationCommand(verb="move", element="my_element", to="actor")
        assert cmd.verb == "move"
        assert cmd.element == "my_element"
        assert cmd.to == "actor"

        # delete
        cmd = SimulationCommand(verb="delete", element="my_element")
        assert cmd.verb == "delete"
        assert cmd.element == "my_element"

    def test_simulation_result_model(self):
        """SimulationResult can be constructed with required fields."""
        from archskillkit.application.models.simulation import SimulationResult

        result = SimulationResult(
            verb="delete",
            base_snapshot_id="abc123",
            base_snapshot_after_id="abc123",
            base_unchanged=True,
            fork_id="simulation-123",
            project_id="test-project",
            recommendation="allowed",
        )
        assert result.verb == "delete"
        assert result.base_snapshot_id == "abc123"
        assert result.base_unchanged is True
        assert result.recommendation == "allowed"
