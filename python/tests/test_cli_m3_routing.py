"""Tests for V2.5 M3 CLI routing: distill_sensors, mine_conformance,
promote_sensor, reject_sensor.

Verifies that the delivery adapter routes through the application layer
when ``world._arch_app`` is set (composition-root path) and falls back
to a direct path otherwise. This is the gate-keeper for APP-COVERAGE-001.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


class _FakeWorld:
    """Minimal fake world with ``_arch_app`` injection point."""

    def __init__(self, app=None):
        self._arch_app = app
        self.db_path = MagicMock(exists=MagicMock(return_value=True))
        self.project_id = "fake-project"
        self.root = Path("/tmp/fake")
        self.calls = []

    def __enter__(self):
        self.calls.append("enter")
        return self

    def __exit__(self, *args):
        self.calls.append("exit")
        return False


class _FakeApp:
    """Records calls to distill_sensors/mine_conformance/promote_sensor/reject_sensor."""

    def __init__(self):
        self.distill_sensors = MagicMock()
        self.mine_conformance = MagicMock()
        self.promote_sensor = MagicMock()
        self.reject_sensor = MagicMock()


class TestDistillSensorsRouting:
    def _make_args(self, **kwargs):
        return SimpleNamespace(
            repo="/tmp/fake",
            min_runs=kwargs.get("min_runs", 2),
            min_occurrences=kwargs.get("min_occurrences", 2),
            record=kwargs.get("record", False),
        )

    def test_routes_through_app_when_arch_app_set(self):
        """When world._arch_app is set, handle() calls app.distill_sensors(cmd)."""
        from archskillkit.delivery.cli import distill_sensors
        from archskillkit.application.models.sensors import (
            DistillSensorsCommand,
            SensorDistillResult,
        )

        fake_app = _FakeApp()
        fake_app.distill_sensors.return_value = SensorDistillResult(
            schema="arch-skillkit/sensor-distillation-v1",
            min_runs=2,
            min_occurrences=2,
            candidates=[],
            recorded=False,
        )
        world = _FakeWorld(app=fake_app)

        with patch("archskillkit.application.models.sensors.SensorDistillResult") as mock_result:
            mock_result.return_value.model_dump = MagicMock(return_value={"schema": "x"})
            rc = distill_sensors.handle(self._make_args(), world)

        assert rc == 0
        fake_app.distill_sensors.assert_called_once()
        cmd = fake_app.distill_sensors.call_args[0][0]
        assert isinstance(cmd, DistillSensorsCommand)
        assert cmd.min_runs == 2
        assert cmd.min_occurrences == 2
        assert cmd.record is False

    def test_falls_back_to_direct_when_no_arch_app(self):
        """When world._arch_app is None, handle() uses the _direct_distill fallback."""
        from archskillkit.delivery.cli import distill_sensors

        world = _FakeWorld(app=None)

        with patch.object(distill_sensors, "_direct_distill") as mock_direct:
            mock_direct.return_value.model_dump = MagicMock(return_value={"schema": "x"})
            rc = distill_sensors.handle(self._make_args(record=True), world)

        assert rc == 0
        mock_direct.assert_called_once()


class TestMineConformanceRouting:
    def _make_args(self, **kwargs):
        return SimpleNamespace(
            repo="/tmp/fake",
            min_support=kwargs.get("min_support", 3),
        )

    def test_routes_through_app_when_arch_app_set(self):
        from archskillkit.delivery.cli import mine_conformance
        from archskillkit.application.models.conformance import (
            MineConformanceCommand,
            MineConformanceResult,
        )

        fake_app = _FakeApp()
        fake_app.mine_conformance.return_value = MineConformanceResult(
            schema="arch-skillkit/conformance-mining-v1",
            project_id="p",
            min_support=3,
            candidates=[],
        )
        world = _FakeWorld(app=fake_app)

        with patch("archskillkit.application.models.conformance.MineConformanceResult") as mock_result:
            mock_result.return_value.model_dump = MagicMock(return_value={"schema": "x"})
            rc = mine_conformance.handle(self._make_args(), world)

        assert rc == 0
        fake_app.mine_conformance.assert_called_once()
        cmd = fake_app.mine_conformance.call_args[0][0]
        assert isinstance(cmd, MineConformanceCommand)
        assert cmd.min_support == 3


class TestPromoteSensorRouting:
    def _make_args(self, **kwargs):
        return SimpleNamespace(
            repo="/tmp/fake",
            candidate_dir=kwargs.get("candidate_dir", Path("/tmp/cand")),
            min_precision=kwargs.get("min_precision", 0.9),
            min_recall=kwargs.get("min_recall", 0.9),
        )

    def test_routes_through_app_when_arch_app_set(self):
        from archskillkit.delivery.cli import promote_sensor
        from archskillkit.application.models.sensors import (
            PromoteSensorCommand,
            SensorPromoteResult,
        )

        fake_app = _FakeApp()
        fake_app.promote_sensor.return_value = SensorPromoteResult(
            schema="arch-skillkit/sensor-promote-v1",
            sensor_id="s1",
            rule_id="r1",
            evaluation={"evaluated": True, "precision": 1.0, "recall": 1.0},
        )
        world = _FakeWorld(app=fake_app)

        with patch("archskillkit.application.models.sensors.SensorPromoteResult") as mock_result:
            mock_result.return_value.model_dump = MagicMock(return_value={"schema": "x"})
            rc = promote_sensor.handle(self._make_args(), world)

        assert rc == 0
        fake_app.promote_sensor.assert_called_once()
        cmd = fake_app.promote_sensor.call_args[0][0]
        assert isinstance(cmd, PromoteSensorCommand)
        assert cmd.candidate_dir == "/tmp/cand"


class TestRejectSensorRouting:
    def _make_args(self, **kwargs):
        return SimpleNamespace(
            repo="/tmp/fake",
            sensor_id=kwargs.get("sensor_id", "s1"),
            reason=kwargs.get("reason", ""),
        )

    def test_routes_through_app_when_arch_app_set(self):
        from archskillkit.delivery.cli import reject_sensor
        from archskillkit.application.models.sensors import (
            RejectSensorCommand,
            SensorRejectResult,
        )

        fake_app = _FakeApp()
        fake_app.reject_sensor.return_value = SensorRejectResult(
            schema="arch-skillkit/sensor-reject-v1",
            sensor_id="s1",
            status="rejected",
            rejection_reason="",
        )
        world = _FakeWorld(app=fake_app)

        with patch("archskillkit.application.models.sensors.SensorRejectResult") as mock_result:
            mock_result.return_value.model_dump = MagicMock(return_value={"schema": "x"})
            rc = reject_sensor.handle(self._make_args(), world)

        assert rc == 0
        fake_app.reject_sensor.assert_called_once()
        cmd = fake_app.reject_sensor.call_args[0][0]
        assert isinstance(cmd, RejectSensorCommand)
        assert cmd.sensor_id == "s1"

    def test_returns_1_on_value_error_from_fallback(self):
        from archskillkit.delivery.cli import reject_sensor

        world = _FakeWorld(app=None)
        with patch.object(reject_sensor, "_direct_reject", side_effect=ValueError("not found")):
            rc = reject_sensor.handle(self._make_args(sensor_id="missing"), world)
        assert rc == 1


class TestAppCoverageCounted:
    """Smoke check: the 4 refactored modules all parse and have a `handle` that
    routes through ``world._arch_app`` when set."""

    @pytest.mark.parametrize("module_name", [
        "distill_sensors",
        "mine_conformance",
        "promote_sensor",
        "reject_sensor",
    ])
    def test_handle_routes_via_arch_app(self, module_name):
        import importlib
        import inspect

        mod = importlib.import_module(f"archskillkit.delivery.cli.{module_name}")
        src = inspect.getsource(mod.handle)
        assert "_arch_app" in src, f"{module_name}.handle must check world._arch_app"

    @pytest.mark.parametrize("module_name", [
        "distill_sensors",
        "mine_conformance",
        "promote_sensor",
        "reject_sensor",
    ])
    def test_handle_has_fallback(self, module_name):
        import importlib
        import inspect

        mod = importlib.import_module(f"archskillkit.delivery.cli.{module_name}")
        mod_src = inspect.getsource(mod)
        assert "_direct_" in mod_src, (
            f"{module_name} must have a _direct_* fallback for non-bootstrap invocation"
        )
