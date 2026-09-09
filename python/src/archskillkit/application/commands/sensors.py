"""Sensor application service (V2.5 M2, ADR-0049).

Canonical application-layer implementation of the sensor workflow:
distill, promote, reject.
"""

from __future__ import annotations

import json as _json
from typing import TYPE_CHECKING

from archskillkit.application.models.sensors import (
    DistillSensorsCommand,
    PromoteSensorCommand,
    RejectSensorCommand,
    SensorDistillResult,
    SensorPromoteResult,
    SensorRejectResult,
)

if TYPE_CHECKING:
    from archskillkit.world import ArchitectureWorld


class SensorApplicationService:
    """Application-layer implementation of the sensor workflow.

    Implements three use cases: distill sensors, promote sensor candidates,
    and reject sensor candidates.
    """

    def __init__(self, world: ArchitectureWorld) -> None:
        self._world = world

    def distill_sensors(self, cmd: DistillSensorsCommand) -> SensorDistillResult:
        """Detect repeated LLM inferences and propose SensorCandidates.

        Parameters
        ----------
        cmd
            DistillSensorsCommand with min_runs, min_occurrences, record.

        Returns
        -------
        SensorDistillResult
            Distillation result with candidate list.
        """
        from archskillkit.sensor_distiller import distill

        with self._world:
            candidates = distill(
                self._world,
                min_runs=cmd.min_runs,
                min_occurrences=cmd.min_occurrences,
            )
            if cmd.record:
                for c in candidates:
                    existing = self._world.find_objects(
                        "sensor_candidate",
                        sensor_id=c.sensor_id,
                    )
                    if existing:
                        continue
                    self._world.add_object(
                        "sensor_candidate",
                        {
                            "sensor_id": c.sensor_id,
                            "title": c.title,
                            "detector_kind": c.detector.engine,
                            "detector_rule": c.detector.rule,
                            "language": c.language,
                            "origin_run_ids": c.origin_run_ids,
                            "status": c.status,
                            "positives": c.positives,
                            "negatives": c.negatives,
                        },
                    )

        return SensorDistillResult(
            schema="arch-skillkit/sensor-distillation-v1",
            min_runs=cmd.min_runs,
            min_occurrences=cmd.min_occurrences,
            candidates=[_json.loads(c.canonical_json()) for c in candidates],
            recorded=cmd.record,
        )

    def promote_sensor(self, cmd: PromoteSensorCommand) -> SensorPromoteResult:
        """Promote a SensorCandidate to a deterministic sensor rule.

        Parameters
        ----------
        cmd
            PromoteSensorCommand with candidate_dir and thresholds.

        Returns
        -------
        SensorPromoteResult
            Promotion result with evaluation and rule_id.
        """
        from pathlib import Path

        from archskillkit.sensor_candidate import evaluate_sensor, meets_threshold

        candidate_dir = Path(cmd.candidate_dir)
        candidate_path = candidate_dir / "candidate.json"

        if not candidate_dir.exists():
            raise FileNotFoundError(f"candidate directory not found: {candidate_dir}")
        if not candidate_path.exists():
            raise FileNotFoundError(f"candidate.json not found in {candidate_dir}")

        # Evaluate the sensor against its fixtures
        eval_result = evaluate_sensor(candidate_dir)
        eval_dict = eval_result.model_dump()

        if not eval_result.evaluated:
            return SensorPromoteResult(
                schema="arch-skillkit/sensor-promote-v1",
                sensor_id=candidate_dir.name,
                rule_id=None,
                evaluation=eval_dict,
            )

        # Check thresholds
        thresholds_met = meets_threshold(
            eval_result,
            min_precision=cmd.min_precision,
            min_recall=cmd.min_recall,
        )
        eval_dict["thresholds_met"] = thresholds_met
        eval_dict["min_precision"] = cmd.min_precision
        eval_dict["min_recall"] = cmd.min_recall

        if not thresholds_met:
            return SensorPromoteResult(
                schema="arch-skillkit/sensor-promote-v1",
                sensor_id=candidate_dir.name,
                rule_id=None,
                evaluation=eval_dict,
            )

        # Load candidate for metadata
        raw = candidate_path.read_text()
        cand_dict = _json.loads(raw)

        # Record the sensor rule in the world
        sensor_id = cand_dict.get("sensor_id", candidate_dir.name)
        title = cand_dict.get("title", sensor_id)
        detector = cand_dict.get("detector", {})
        detector_kind = detector.get("engine", "ast-grep")
        detector_rule = detector.get("rule", "")
        language = cand_dict.get("language", "python")
        origin_run_ids = cand_dict.get("origin_run_ids", [])

        with self._world:
            rule_id = self._world.record_sensor_rule(
                sensor_id=sensor_id,
                title=title,
                detector_kind=detector_kind,
                detector_rule=detector_rule,
                language=language,
                precision=eval_result.precision,
                recall=eval_result.recall,
                origin_run_ids=origin_run_ids,
            )

        return SensorPromoteResult(
            schema="arch-skillkit/sensor-promote-v1",
            sensor_id=sensor_id,
            rule_id=rule_id,
            evaluation=eval_dict,
        )

    def reject_sensor(self, cmd: RejectSensorCommand) -> SensorRejectResult:
        """Reject a SensorCandidate.

        Parameters
        ----------
        cmd
            RejectSensorCommand with sensor_id and reason.

        Returns
        -------
        SensorRejectResult
            Rejection confirmation.
        """
        # Find the candidate object
        candidates = self._world.find_objects("sensor_candidate")
        candidate_obj = None
        for obj in candidates:
            data = obj.get("data") or {}
            if data.get("sensor_id") == cmd.sensor_id:
                candidate_obj = obj
                break

        if candidate_obj is None:
            raise ValueError(f"no sensor candidate found with sensor_id={cmd.sensor_id!r}")

        obj_id = candidate_obj["id"]
        with self._world:
            self._world.set_object_fields(
                obj_id,
                {"status": "rejected", "rejection_reason": cmd.reason},
            )

        return SensorRejectResult(
            schema="arch-skillkit/sensor-reject-v1",
            sensor_id=cmd.sensor_id,
            status="rejected",
            rejection_reason=cmd.reason,
        )
