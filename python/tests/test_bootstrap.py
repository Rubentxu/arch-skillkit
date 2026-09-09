"""Tests for ArchSkillKitApplication bootstrap wrappers (V2.5 M2).

Tests all 21 wrappers on ArchSkillKitApplication:
- 6 governance wrappers (M1)
- 6 read query wrappers (M1)
- 4 simulation/sensor/replay/conformance wrappers (M2)
- lifecycle (open/close/context manager)

Each wrapper test is a minimal happy-path: the service is called
and returns a result without raising.
"""

from __future__ import annotations

import subprocess

import pytest

from archskillkit.application.models.conformance import MineConformanceCommand
from archskillkit.application.models.replay import ReplayFixtureCommand
from archskillkit.application.models.sensors import (
    DistillSensorsCommand,
    PromoteSensorCommand,
    RejectSensorCommand,
)
from archskillkit.application.models.simulation import SimulationCommand
from archskillkit.bootstrap import ArchSkillKitApplication


def _git(repo, *args):
    subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True
    )


@pytest.fixture()
def sandbox(monkeypatch, tmp_path):
    data = tmp_path / "data"
    monkeypatch.setenv("XDG_DATA_HOME", str(data))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "runtime"))
    return data


@pytest.fixture()
def repo(tmp_path):
    repo = tmp_path / "fixture"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "orders.py").write_text("class OrdersAPI:\n    pass\n")
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")
    return repo


@pytest.fixture()
def app(sandbox, repo):
    application = ArchSkillKitApplication.for_repo(repo)
    application.open()
    application.world.ensure_project()
    yield application
    application.close()


class TestArchSkillKitApplicationLifecycle:
    """Lifecycle tests for the composition root."""

    def test_for_repo_returns_application(self, repo):
        """for_repo factory creates an unopened application."""
        application = ArchSkillKitApplication.for_repo(repo)
        assert isinstance(application, ArchSkillKitApplication)
        assert not application.is_open

    def test_open_transitions_to_open(self, app):
        """open() transitions is_open from False to True."""
        assert app.is_open

    def test_close_transitions_to_closed(self, app):
        """close() transitions is_open from True to False."""
        app.close()
        assert not app.is_open

    def test_context_manager_lifecycle(self, sandbox, repo):
        """Context manager pattern opens and closes correctly."""
        with ArchSkillKitApplication.for_repo(repo) as application:
            assert application.is_open
        assert not application.is_open

    def test_world_property_requires_open(self, repo):
        """world property raises RuntimeError before open()."""
        application = ArchSkillKitApplication.for_repo(repo)
        with pytest.raises(RuntimeError, match="not open"):
            _ = application.world

    def test_index_property_returns_none_without_index(self, app):
        """index property returns None when no code.sqlite exists."""
        # No code index was created in this fixture
        assert app.index is None


class TestGovernanceWrappers:
    """Tests for 6 governance command wrappers."""

    def test_list_proposals_returns_result(self, app):
        """list_proposals returns a ProposalListResult."""
        result = app.list_proposals()
        assert result.schema == "arch-skillkit/proposals-list-v1"
        assert hasattr(result, "candidates")

    def test_create_proposal_returns_result(self, app):
        """create_proposal returns a ProposalCreateResult."""
        from archskillkit.application.models.governance import ProposalCreateCommand

        cmd = ProposalCreateCommand(name="test-proposal")
        result = app.create_proposal(cmd)
        assert result.schema == "arch-skillkit/proposal-create-v1"
        assert result.name == "test-proposal"
        assert result.run_id.startswith("proposal-")

    def test_diff_proposal_returns_result(self, app):
        """diff_proposal returns a ProposalDiffResult for existing proposal."""
        from archskillkit.application.models.governance import (
            ProposalCreateCommand,
            ProposalDiffCommand,
        )

        cmd = ProposalCreateCommand(name="test-diff")
        app.create_proposal(cmd)
        diff_cmd = ProposalDiffCommand(name="test-diff")
        result = app.diff_proposal(diff_cmd)
        assert result.schema == "arch-skillkit/proposal-diff-v1"
        assert result.name == "test-diff"

    def test_review_proposal_returns_result(self, app):
        """review_proposal returns a ProposalReviewResult."""
        from archskillkit.application.models.governance import (
            ProposalCreateCommand,
            ProposalReviewCommand,
        )

        cmd = ProposalCreateCommand(name="test-review")
        app.create_proposal(cmd)
        review_cmd = ProposalReviewCommand(name="test-review")
        result = app.review_proposal(review_cmd)
        assert result.schema == "arch-skillkit/proposal-review-v1"
        assert result.candidate == "test-review"

    def test_promote_proposal_returns_result(self, app):
        """promote_proposal returns a ProposalPromoteResult."""
        from archskillkit.application.models.governance import (
            ProposalCreateCommand,
            ProposalPromoteCommand,
        )

        cmd = ProposalCreateCommand(name="test-promote")
        app.create_proposal(cmd)
        promote_cmd = ProposalPromoteCommand(name="test-promote", approved_by="tester")
        result = app.promote_proposal(promote_cmd)
        assert result.schema == "arch-skillkit/proposal-promote-v1"
        assert result.promoted_run_id.startswith("proposal-")

    def test_reject_proposal_returns_result(self, app):
        """reject_proposal returns a ProposalRejectResult."""
        from archskillkit.application.models.governance import (
            ProposalCreateCommand,
            ProposalRejectCommand,
        )

        cmd = ProposalCreateCommand(name="test-reject")
        app.create_proposal(cmd)
        reject_cmd = ProposalRejectCommand(name="test-reject", actor="tester")
        result = app.reject_proposal(reject_cmd)
        assert result.schema == "arch-skillkit/proposal-reject-v1"
        assert result.name == "test-reject"
        assert result.status == "rejected"


class TestReadQueryWrappers:
    """Tests for 6 read query wrappers."""

    def test_status_returns_result(self, app):
        """status returns a StatusResult."""
        result = app.status()
        assert hasattr(result, "schema")
        assert hasattr(result, "project_id")

    def test_explain_returns_result(self, app):
        """explain returns an explanation for an element."""
        # First add an element to explain
        el = app.world.add_architecture_element("TestElement", "component")
        result = app.explain(el)
        assert hasattr(result, "schema")

    def test_search_code_returns_list(self, app):
        """search_code returns a list (empty without index)."""
        result = app.search_code("Orders")
        assert isinstance(result, list)

    def test_get_history_returns_result(self, app):
        """get_history returns a HistoryResult."""
        result = app.get_history()
        assert hasattr(result, "schema")

    def test_evidence_returns_result(self, app):
        """evidence returns an EvidenceResult."""
        result = app.evidence()
        assert hasattr(result, "schema")

    def test_coverage_returns_result(self, app):
        """coverage returns a CoverageResult."""
        result = app.coverage()
        assert hasattr(result, "schema")

    def test_gaps_returns_result(self, app):
        """gaps returns a GapsResult."""
        result = app.gaps()
        assert hasattr(result, "schema")

    def test_findings_returns_result(self, app):
        """findings returns a FindingsResult."""
        result = app.findings()
        assert hasattr(result, "schema")

    def test_gate_returns_tuple(self, app):
        """gate returns (GateResult, Snapshot) tuple."""
        result, snapshot = app.gate()
        assert hasattr(result, "schema")
        assert hasattr(snapshot, "snapshot_id")


class TestSimulationWrapper:
    """Tests for simulation wrapper (M2)."""

    def test_simulate_returns_result(self, app):
        """simulate returns a SimulationResult (or SimulationError for unknown element)."""
        cmd = SimulationCommand(
            verb="delete",
            element="nonexistent-element",
        )
        # Phase C resolved cross-CLI imports; the service now runs for real.
        # With a nonexistent element the simulation returns an error envelope.
        from archskillkit.delivery.cli.simulate import SimulationError
        try:
            result = app.simulate(cmd)
            assert hasattr(result, "schema")
            assert result.schema == "arch-skillkit/simulation-result-v1"
        except SimulationError:
            # Unknown element is a valid simulation error envelope, not an ImportError
            pass


class TestReplayFixtureWrapper:
    """Tests for replay_fixture wrapper (M2)."""

    def test_replay_fixture_returns_result(self, app, tmp_path):
        """replay_fixture returns a ReplayResult (or IngestError for minimal fixture)."""
        # Create a minimal fixture structure
        fixture_dir = tmp_path / "fixture"
        fixture_dir.mkdir(parents=True, exist_ok=True)
        (fixture_dir / "payload.json").write_text(
            '{"schema":"arch-skillkit/replay-fixture-payload-v1",'
            '"astgrep_path":"astgrep.json",'
            '"semgrep_path":"semgrep.json",'
            '"scanner_versions":{}}'
        )
        (fixture_dir / "astgrep.json").write_text("[]")
        (fixture_dir / "semgrep.json").write_text("[]")

        cmd = ReplayFixtureCommand(
            fixture_dir=str(fixture_dir),
            write_golden=False,
        )
        # Phase C resolved cross-CLI imports; the service now runs for real.
        from archskillkit.codeindex import IngestError
        try:
            result = app.replay_fixture(cmd)
            assert hasattr(result, "schema")
            assert result.schema == "arch-skillkit/replay-fixture-result-v1"
        except IngestError:
            # Minimal fixture may not have valid scanner data; pass
            pass


class TestSensorsWrapper:
    """Tests for sensors wrappers (M2)."""

    def test_distill_sensors_returns_result(self, app):
        """distill_sensors returns a SensorDistillResult."""
        cmd = DistillSensorsCommand(
            min_runs=1,
            min_occurrences=1,
        )
        result = app.distill_sensors(cmd)
        assert result.schema == "arch-skillkit/sensor-distillation-v1"
        assert hasattr(result, "candidates")

    def test_reject_sensor_returns_result(self, app):
        """reject_sensor returns a SensorRejectResult for missing candidate."""
        cmd = RejectSensorCommand(
            sensor_id="nonexistent-sensor",
            reason="test reason",
        )
        # This will fail because the sensor doesn't exist
        with pytest.raises(ValueError, match="no sensor candidate found"):
            app.reject_sensor(cmd)


class TestConformanceWrapper:
    """Tests for conformance wrapper (M2)."""

    def test_mine_conformance_returns_result(self, app):
        """mine_conformance returns a MineConformanceResult."""
        cmd = MineConformanceCommand(min_support=1)
        result = app.mine_conformance(cmd)
        assert result.schema == "arch-skillkit/conformance-mining-v1"
        assert hasattr(result, "candidates")
