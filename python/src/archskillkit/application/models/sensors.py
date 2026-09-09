"""Sensor command DTOs (V2.5 M2, ADR-0049).

Schema-bound input/output for the SensorApplicationService.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DistillSensorsCommand(BaseModel):
    """Input for running the Sensor Distiller."""

    model_config = ConfigDict(extra="forbid")

    min_runs: int = Field(
        default=2,
        ge=1,
        description="Minimum distinct runs a signature must appear in (default: 2)",
    )
    min_occurrences: int = Field(
        default=2,
        ge=1,
        description="Minimum total claims across all runs (default: 2)",
    )
    record: bool = Field(
        default=False,
        description="Record each candidate as a sensor_candidate world object",
    )


class PromoteSensorCommand(BaseModel):
    """Input for promoting a SensorCandidate to a deterministic sensor."""

    model_config = ConfigDict(extra="forbid")

    candidate_dir: str = Field(description="Directory containing candidate.json and fixture files")
    min_precision: float = Field(
        default=0.9,
        ge=0.0,
        le=1.0,
        description="Minimum precision threshold (default: 0.9)",
    )
    min_recall: float = Field(
        default=0.9,
        ge=0.0,
        le=1.0,
        description="Minimum recall threshold (default: 0.9)",
    )


class RejectSensorCommand(BaseModel):
    """Input for rejecting a SensorCandidate."""

    model_config = ConfigDict(extra="forbid")

    sensor_id: str = Field(description="sensor_id of the candidate to reject")
    reason: str = Field(
        default="",
        description="Reason for rejection (recorded in the world)",
    )


class SensorDistillResult(BaseModel):
    """Sensor Distillation result envelope."""

    model_config = ConfigDict(extra="forbid")

    schema: str = "arch-skillkit/sensor-distillation-v1"
    min_runs: int
    min_occurrences: int
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    recorded: bool


class SensorPromoteResult(BaseModel):
    """Sensor promotion result envelope."""

    model_config = ConfigDict(extra="forbid")

    schema: str = "arch-skillkit/sensor-promote-v1"
    sensor_id: str
    rule_id: str | None = None
    evaluation: dict[str, Any] = Field(default_factory=dict)


class SensorRejectResult(BaseModel):
    """Sensor rejection result envelope."""

    model_config = ConfigDict(extra="forbid")

    schema: str = "arch-skillkit/sensor-reject-v1"
    sensor_id: str
    status: str = "rejected"
    rejection_reason: str
