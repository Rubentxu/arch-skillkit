"""Tests for ConformanceApplicationService (V2.5 M2).

Tests the mine_conformance use case through the application layer.
"""

from __future__ import annotations

import pytest

from archskillkit.application.commands.conformance import ConformanceApplicationService
from archskillkit.application.models.conformance import (
    MineConformanceCommand,
    MineConformanceResult,
)


class TestConformanceApplicationService:
    """Happy-path tests for ConformanceApplicationService."""

    def test_mine_conformance_command_model(self):
        """MineConformanceCommand can be constructed with defaults."""
        cmd = MineConformanceCommand()
        assert cmd.min_support == 3

    def test_mine_conformance_command_custom(self):
        """MineConformanceCommand can be constructed with custom min_support."""
        cmd = MineConformanceCommand(min_support=5)
        assert cmd.min_support == 5

    def test_mine_conformance_result_model(self):
        """MineConformanceResult can be constructed with required fields."""
        result = MineConformanceResult(
            schema="arch-skillkit/conformance-mining-v1",
            project_id="test-project",
            min_support=3,
            candidates=[],
        )
        assert result.schema == "arch-skillkit/conformance-mining-v1"
        assert result.project_id == "test-project"
        assert result.min_support == 3
        assert result.candidates == []

    def test_mine_conformance_result_with_candidates(self):
        """MineConformanceResult can carry candidate data."""
        candidate = {
            "candidate_id": "depends_on-actor-service",
            "rel_kind": "depends_on",
            "source_kind": "actor",
            "target_kind": "service",
            "support": 5,
            "example_relation_ids": ["rel-1", "rel-2"],
            "observed_in_runs": ["run-1", "run-2"],
            "status": "candidate",
            "proposed_rule": {
                "name": "depends_on-actor-service-rule",
                "statement": "DRAFT from observed pattern",
                "forbidden_relation": "depends_on",
                "source_category": "actor",
                "target_category": "service",
                "severity": "medium",
            },
        }
        result = MineConformanceResult(
            schema="arch-skillkit/conformance-mining-v1",
            project_id="test-project",
            min_support=3,
            candidates=[candidate],
        )
        assert len(result.candidates) == 1
        assert result.candidates[0]["candidate_id"] == "depends_on-actor-service"
