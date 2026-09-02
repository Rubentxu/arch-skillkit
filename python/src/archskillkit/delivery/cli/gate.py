"""`archskillkit gate` — governance gate over the fitness profile
(V2.4 M3, docs/v2/55 §2, §10).

Deterministic decision: same world + same thresholds + same waivers ->
identical verdict, byte for byte. Exit codes: 0 pass, 1 fail (with the
failed dimensions named in the JSON). Read-only towards the world.
"""

from __future__ import annotations

import argparse
import json
import sys

from archskillkit.application.queries.fitness import (
    FitnessThresholds,
    evaluate_gate,
)
from archskillkit.application.snapshot_builder import build_snapshot
from archskillkit.codeindex import CodeIndex
from archskillkit.runtime_state.run_ledger import RunLedger
from archskillkit.runtime_state.waivers import WaiverLedger
from archskillkit.world import ArchitectureWorld

NAME = "gate"
NEEDS_WORLD = True


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        NAME, help="evaluate the architecture fitness gate (JSON;"
        " exit 0 pass / 1 fail)")
    p.add_argument("--repo", required=True)
    p.add_argument("--min-coverage", type=float, default=0.8,
                   help="minimum evidence coverage (0..1)")
    p.add_argument("--max-unknowns", type=int, default=0)
    p.add_argument("--max-findings", type=int, default=0)
    p.add_argument("--max-run-age-days", type=int, default=30)


def handle(args: argparse.Namespace, world: ArchitectureWorld) -> int:
    if not world.db_path.exists():
        print(f"error: no Architecture World for {world.project_id} "
              f"(run: archskillkit init --repo {world.root or '.'})",
              file=sys.stderr)
        return 1
    thresholds = FitnessThresholds(
        min_evidence_coverage=args.min_coverage,
        max_unknowns=args.max_unknowns,
        max_findings=args.max_findings,
        max_run_age_days=args.max_run_age_days,
    )
    db = world.workspace / "code.sqlite"
    index = CodeIndex(db).open() if db.exists() else None
    ledger = RunLedger()  # state-root ledger; absence reads as empty
    try:
        with world:
            snapshot = build_snapshot(world, code_index=index)
            result = evaluate_gate(world, snapshot,
                                   thresholds=thresholds,
                                   ledger=ledger,
                                   waivers=WaiverLedger())
    finally:
        if index is not None:
            index.close()
    print(json.dumps(result.model_dump(), indent=2))
    return result.exit_code
