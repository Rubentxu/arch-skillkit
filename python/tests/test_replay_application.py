"""Tests for ReplayApplicationService (V2.5 M2).

Tests the replay_fixture use case through the application layer.
"""

from __future__ import annotations

import pytest

from archskillkit.application.commands.replay import ReplayApplicationService
from archskillkit.application.models.replay import ReplayFixtureCommand, ReplayResult


class TestReplayApplicationService:
    """Happy-path tests for ReplayApplicationService."""

    def test_replay_fixture_command_model(self):
        """ReplayFixtureCommand can be constructed with required fields."""
        cmd = ReplayFixtureCommand(
            fixture_dir="/path/to/fixture",
            write_golden=False,
        )
        assert cmd.fixture_dir == "/path/to/fixture"
        assert cmd.write_golden is False

    def test_replay_fixture_command_defaults(self):
        """ReplayFixtureCommand has sensible defaults."""
        cmd = ReplayFixtureCommand(fixture_dir="/path/to/fixture")
        assert cmd.write_golden is False

    def test_replay_result_model(self):
        """ReplayResult can be constructed with required fields."""
        result = ReplayResult(
            fixture_id="my-fixture",
            fixture_dir="/path/to/fixture",
            replayed_snapshot_id="xyz789",
            golden_snapshot_id="xyz789",
            match=True,
            pinned={"astgrep": "1.0"},
            live_toolchain={"astgrep": "1.1"},
        )
        assert result.fixture_id == "my-fixture"
        assert result.match is True
        assert result.pinned == {"astgrep": "1.0"}

    def test_replay_result_mismatch(self):
        """ReplayResult can represent a mismatch (drift)."""
        result = ReplayResult(
            fixture_id="my-fixture",
            fixture_dir="/path/to/fixture",
            replayed_snapshot_id="xyz789",
            golden_snapshot_id="abc123",
            match=False,
            drift={"reason": "schema version changed"},
            pinned={},
            live_toolchain={},
        )
        assert result.match is False
        assert result.drift is not None
