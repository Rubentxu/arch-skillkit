"""`archskillkit promote-sensor` — promote a SensorCandidate to a deterministic sensor (M7).

Promotes a sensor candidate to an active deterministic sensor rule when:
  1. The candidate has non-empty positive AND negative fixture lists.
  2. ``evaluate_sensor`` runs successfully against those fixtures.
  3. Both precision AND recall meet the configured thresholds.

On success, records the sensor as a ``sensor_rule`` object in the world.
On failure, prints the evaluation result with precision/recall so the human
knows why promotion was rejected.

Usage:
  archskillkit promote-sensor --repo . --candidate-dir /path/to/candidate [--min-precision 0.9] [--min-recall 0.9]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from archskillkit.sensor_candidate import (
    evaluate_sensor,
    meets_threshold,
)
from archskillkit.world import ArchitectureWorld

NAME = "promote-sensor"
NEEDS_WORLD = True


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        NAME,
        help="promote a SensorCandidate to a deterministic sensor rule",
    )
    p.add_argument(
        "--repo",
        required=True,
        help="path to the arch-skillkit repository",
    )
    p.add_argument(
        "--candidate-dir",
        required=True,
        type=Path,
        help="directory containing candidate.json and fixture files",
    )
    p.add_argument(
        "--min-precision",
        type=float,
        default=0.9,
        help="minimum precision threshold (default: 0.9)",
    )
    p.add_argument(
        "--min-recall",
        type=float,
        default=0.9,
        help="minimum recall threshold (default: 0.9)",
    )


def handle(args: argparse.Namespace, world: ArchitectureWorld) -> int:
    candidate_dir = args.candidate_dir
    candidate_path = candidate_dir / "candidate.json"

    if not candidate_dir.exists():
        print(f"error: candidate directory not found: {candidate_dir}", file=sys.stderr)
        return 1
    if not candidate_path.exists():
        print(f"error: candidate.json not found in {candidate_dir}", file=sys.stderr)
        return 1

    # Evaluate the sensor against its fixtures
    eval_result = evaluate_sensor(candidate_dir)
    eval_dict = eval_result.model_dump()

    if not eval_result.evaluated:
        print(
            f"error: evaluation failed: {eval_result.reason_code} — {eval_result.detail}",
            file=sys.stderr,
        )
        print(json.dumps({"evaluation": eval_dict}, indent=2))
        return 1

    # Check thresholds
    thresholds_met = meets_threshold(
        eval_result, min_precision=args.min_precision, min_recall=args.min_recall
    )
    eval_dict["thresholds_met"] = thresholds_met
    eval_dict["min_precision"] = args.min_precision
    eval_dict["min_recall"] = args.min_recall

    if not thresholds_met:
        print(
            f"error: thresholds not met — precision={eval_result.precision:.3f} "
            f"(min {args.min_precision}), recall={eval_result.recall:.3f} "
            f"(min {args.min_recall})",
            file=sys.stderr,
        )
        print(json.dumps({"evaluation": eval_dict}, indent=2))
        return 1

    # Load candidate for metadata
    try:
        raw = candidate_path.read_text()
        import json as _json
        cand_dict = _json.loads(raw)
    except (OSError, _json.JSONDecodeError) as exc:
        print(f"error: could not read candidate.json: {exc}", file=sys.stderr)
        return 1

    # Record the sensor rule in the world
    sensor_id = cand_dict.get("sensor_id", candidate_dir.name)
    title = cand_dict.get("title", sensor_id)
    detector = cand_dict.get("detector", {})
    detector_kind = detector.get("engine", "ast-grep")
    detector_rule = detector.get("rule", "")
    language = cand_dict.get("language", "python")
    origin_run_ids = cand_dict.get("origin_run_ids", [])

    with world:
        rule_id = world.record_sensor_rule(
            sensor_id=sensor_id,
            title=title,
            detector_kind=detector_kind,
            detector_rule=detector_rule,
            language=language,
            precision=eval_result.precision,
            recall=eval_result.recall,
            origin_run_ids=origin_run_ids,
        )

    result = {
        "schema": "arch-skillkit/sensor-promote-v1",
        "sensor_id": sensor_id,
        "rule_id": rule_id,
        "evaluation": eval_dict,
    }
    print(json.dumps(result, indent=2))
    return 0
