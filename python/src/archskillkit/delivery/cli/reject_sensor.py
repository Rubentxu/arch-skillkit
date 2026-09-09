"""`archskillkit reject-sensor` — reject a SensorCandidate (M7 Learning Architecture).

A candidate can be rejected at any time by a human reviewer. This records the
rejection in the world so the same candidate is not proposed again by the
distiller (the distiller skips candidates whose status is "rejected").

Delivery adapter (V2.5 M3): routes through ``app.reject_sensor()``
(ADR-0057, M2 composition root). Falls back to direct find_objects +
set_object_fields for direct CLI invocation without the bootstrap app.

Usage:
  archskillkit reject-sensor --repo . --sensor-id <id> --reason "high false-positive rate"
"""

from __future__ import annotations

import argparse
import json
import sys

from archskillkit.application.models.sensors import (
    RejectSensorCommand,
    SensorRejectResult,
)
from archskillkit.world import ArchitectureWorld

NAME = "reject-sensor"
NEEDS_WORLD = True


def _direct_reject(world, cmd: RejectSensorCommand) -> SensorRejectResult:
    """Fallback path: invoke find_objects + set_object_fields directly."""
    candidates = world.find_objects("sensor_candidate")
    candidate_obj = None
    for obj in candidates:
        data = obj.get("data") or {}
        if data.get("sensor_id") == cmd.sensor_id:
            candidate_obj = obj
            break

    if candidate_obj is None:
        raise ValueError(
            f"no sensor candidate found with sensor_id={cmd.sensor_id!r}"
        )

    obj_id = candidate_obj["id"]
    with world:
        world.set_object_fields(
            obj_id,
            {"status": "rejected", "rejection_reason": cmd.reason},
        )

    return SensorRejectResult(
        schema="arch-skillkit/sensor-reject-v1",
        sensor_id=cmd.sensor_id,
        status="rejected",
        rejection_reason=cmd.reason,
    )


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        NAME,
        help="reject a SensorCandidate (prevents re-proposal by distiller)",
    )
    p.add_argument("--repo", required=True)
    p.add_argument("--sensor-id", required=True, help="sensor_id of the candidate to reject")
    p.add_argument(
        "--reason",
        default="",
        help="reason for rejection (recorded in the world)",
    )


def handle(args: argparse.Namespace, world: ArchitectureWorld) -> int:
    app = getattr(world, "_arch_app", None)
    cmd = RejectSensorCommand(
        sensor_id=args.sensor_id,
        reason=args.reason,
    )

    try:
        if app is not None:
            result = app.reject_sensor(cmd)
        else:
            result = _direct_reject(world, cmd)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result.model_dump(mode="json"), indent=2))
    return 0
