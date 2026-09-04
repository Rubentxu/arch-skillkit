"""`archskillkit reject-sensor` — reject a SensorCandidate (M7 Learning Architecture).

A candidate can be rejected at any time by a human reviewer. This records the
rejection in the world so the same candidate is not proposed again by the
distiller (the distiller skips candidates whose status is "rejected").

Usage:
  archskillkit reject-sensor --repo . --sensor-id <id> --reason "high false-positive rate"
"""

from __future__ import annotations

import argparse
import json
import sys

from archskillkit.world import ArchitectureWorld

NAME = "reject-sensor"
NEEDS_WORLD = True


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
    sensor_id = args.sensor_id

    # Find the candidate object
    candidates = world.find_objects("sensor_candidate")
    candidate_obj = None
    for obj in candidates:
        data = obj.get("data") or {}
        if data.get("sensor_id") == sensor_id:
            candidate_obj = obj
            break

    if candidate_obj is None:
        print(
            f"error: no sensor candidate found with sensor_id={sensor_id!r}",
            file=sys.stderr,
        )
        return 1

    obj_id = candidate_obj["id"]
    with world:
        world.set_object_fields(
            obj_id,
            {"status": "rejected", "rejection_reason": args.reason},
        )

    print(
        json.dumps(
            {
                "schema": "arch-skillkit/sensor-reject-v1",
                "sensor_id": sensor_id,
                "status": "rejected",
                "rejection_reason": args.reason,
            },
            indent=2,
        )
    )
    return 0
