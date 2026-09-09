"""`archskillkit distill-sensors` — run the Sensor Distiller and emit candidates.

Delivery adapter (docs/v2/55 §2/§4/§5, V2.5 M3): argument parsing →
application layer → JSON output. No architecture logic here (ADR-0045).
Routes through ``app.distill_sensors()`` (ADR-0057, M2 composition root).

Schema output: arch-skillkit/sensor-distillation-v1
"""

from __future__ import annotations

import argparse
import json
import sys

from archskillkit.application.models.sensors import DistillSensorsCommand
from archskillkit.world import ArchitectureWorld

NAME = "distill-sensors"
NEEDS_WORLD = True


def _direct_distill(world, cmd: DistillSensorsCommand, distill):
    """Fallback path: invoke distill() directly when composition root is absent.

    Mirrors the application-layer logic so direct CLI invocation without
    the bootstrap app produces the same result envelope.
    """
    from archskillkit.application.models.sensors import SensorDistillResult

    candidates = distill(
        world,
        min_runs=cmd.min_runs,
        min_occurrences=cmd.min_occurrences,
    )
    if cmd.record:
        for c in candidates:
            existing = world.find_objects("sensor_candidate", sensor_id=c.sensor_id)
            if existing:
                continue
            world.add_object(
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
        candidates=[json.loads(c.canonical_json()) for c in candidates],
        recorded=cmd.record,
    )


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        NAME,
        help="run the Sensor Distiller: detect repeated LLM inferences "
        "and emit SensorCandidate proposals as JSON",
    )
    p.add_argument("--repo", required=True)
    p.add_argument(
        "--min-runs",
        type=int,
        default=2,
        help="minimum distinct runs a signature must appear in (default: 2)",
    )
    p.add_argument(
        "--min-occurrences",
        type=int,
        default=2,
        help="minimum total claims across all runs (default: 2)",
    )
    p.add_argument(
        "--record",
        action="store_true",
        help="record each candidate as a sensor_candidate world object "
        "(enables archskillkit reject-sensor workflow)",
    )


def handle(args: argparse.Namespace, world: ArchitectureWorld) -> int:
    if not world.db_path.exists():
        print(
            f"error: no Architecture World for {world.project_id} "
            f"(run: archskillkit init --repo {world.root or '.'})",
            file=sys.stderr,
        )
        return 1

    # Route through Composition Root when app is available (app bootstrap path).
    # Fall back to direct distill() for direct CLI invocation without app.
    app = getattr(world, "_arch_app", None)
    cmd = DistillSensorsCommand(
        min_runs=args.min_runs,
        min_occurrences=args.min_occurrences,
        record=args.record,
    )

    try:
        with world:
            if app is not None:
                result = app.distill_sensors(cmd)
            else:
                from archskillkit.sensor_distiller import distill
                result = _direct_distill(world, cmd, distill)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(result.model_dump(mode="json"), indent=2))
    return 0
