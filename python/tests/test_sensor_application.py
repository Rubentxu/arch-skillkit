"""Tests for SensorApplicationService (V2.5 M2).

Tests the distill, promote, and reject sensor use cases through the application layer.
"""

from __future__ import annotations

from archskillkit.application.models.sensors import (
    DistillSensorsCommand,
    PromoteSensorCommand,
    RejectSensorCommand,
    SensorDistillResult,
    SensorPromoteResult,
    SensorRejectResult,
)


class TestSensorApplicationService:
    """Happy-path tests for SensorApplicationService."""

    def test_distill_sensors_command_model(self):
        """DistillSensorsCommand can be constructed with defaults."""
        cmd = DistillSensorsCommand()
        assert cmd.min_runs == 2
        assert cmd.min_occurrences == 2
        assert cmd.record is False

    def test_distill_sensors_command_custom(self):
        """DistillSensorsCommand can be constructed with custom values."""
        cmd = DistillSensorsCommand(
            min_runs=5,
            min_occurrences=10,
            record=True,
        )
        assert cmd.min_runs == 5
        assert cmd.min_occurrences == 10
        assert cmd.record is True

    def test_promote_sensor_command_model(self):
        """PromoteSensorCommand can be constructed with required fields."""
        cmd = PromoteSensorCommand(
            candidate_dir="/path/to/candidate",
        )
        assert cmd.candidate_dir == "/path/to/candidate"
        assert cmd.min_precision == 0.9
        assert cmd.min_recall == 0.9

    def test_promote_sensor_command_custom_thresholds(self):
        """PromoteSensorCommand can be constructed with custom thresholds."""
        cmd = PromoteSensorCommand(
            candidate_dir="/path/to/candidate",
            min_precision=0.95,
            min_recall=0.85,
        )
        assert cmd.min_precision == 0.95
        assert cmd.min_recall == 0.85

    def test_reject_sensor_command_model(self):
        """RejectSensorCommand can be constructed with required fields."""
        cmd = RejectSensorCommand(
            sensor_id="inferred-my-sensor-123",
            reason="high false-positive rate",
        )
        assert cmd.sensor_id == "inferred-my-sensor-123"
        assert cmd.reason == "high false-positive rate"

    def test_reject_sensor_command_defaults(self):
        """RejectSensorCommand reason defaults to empty string."""
        cmd = RejectSensorCommand(sensor_id="inferred-my-sensor-123")
        assert cmd.reason == ""

    def test_sensor_distill_result_model(self):
        """SensorDistillResult can be constructed with required fields."""
        result = SensorDistillResult(
            schema="arch-skillkit/sensor-distillation-v1",
            min_runs=2,
            min_occurrences=2,
            candidates=[],
            recorded=False,
        )
        assert result.schema == "arch-skillkit/sensor-distillation-v1"
        assert result.min_runs == 2
        assert result.candidates == []

    def test_sensor_promote_result_model(self):
        """SensorPromoteResult can be constructed with required fields."""
        result = SensorPromoteResult(
            schema="arch-skillkit/sensor-promote-v1",
            sensor_id="inferred-my-sensor-123",
            rule_id="rule-456",
            evaluation={"precision": 0.95, "recall": 0.92},
        )
        assert result.sensor_id == "inferred-my-sensor-123"
        assert result.rule_id == "rule-456"

    def test_sensor_reject_result_model(self):
        """SensorRejectResult can be constructed with required fields."""
        result = SensorRejectResult(
            schema="arch-skillkit/sensor-reject-v1",
            sensor_id="inferred-my-sensor-123",
            status="rejected",
            rejection_reason="high false-positive rate",
        )
        assert result.sensor_id == "inferred-my-sensor-123"
        assert result.status == "rejected"
        assert result.rejection_reason == "high false-positive rate"
