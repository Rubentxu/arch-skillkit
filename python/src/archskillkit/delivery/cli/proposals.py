"""`archskillkit proposals` — candidate workflow (V2.4 M4, docs/v2/59).

The candidate -> review -> promote path:

  fork  ->  review  ->  promote  (or reject-proposal)

  archskillkit fork               --repo PATH --name NAME   create candidate
  archskillkit proposals list     --repo PATH                list candidates
  archskillkit proposals review   --repo PATH --name NAME    evaluate gate
                                                            against the
                                                            candidate vs main
  archskillkit promote            --repo PATH --name NAME --approved-by WHO
  archskillkit reject-proposal    --repo PATH --name NAME --actor WHO

fork / promote / reject-proposal already live in cli.py (legacy path);
this module adds the missing list and review verbs and gives the
workflow a single, schema-bound surface.
"""

from __future__ import annotations

import argparse
import json
import sys

from archskillkit.application.queries.fitness import (
    FitnessThresholds,
    evaluate_gate,
)
from archskillkit.application.queries.report import render_json
from archskillkit.application.snapshot_builder import build_snapshot
from archskillkit.codeindex import CodeIndex
from archskillkit.proposals import (
    structural_diff,
)
from archskillkit.runtime_state.run_ledger import RunLedger
from archskillkit.runtime_state.waivers import WaiverLedger
from archskillkit.world import ArchitectureWorld

NAME = "proposals"
NEEDS_WORLD = True
PROPOSAL_PREFIX = "proposal-"


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        NAME, help="candidate -> review -> promote workflow")
    p.add_argument("--repo", required=True)
    sub = p.add_subparsers(dest="proposals_action", required=True)
    sub.add_parser("list", help="list candidate (proposal-*) runs")
    pr = sub.add_parser("review",
                        help="review a candidate against the fitness"
                        " gate + structural diff")
    pr.add_argument("--name", required=True)
    pr.add_argument("--min-coverage", type=float, default=0.8)
    pr.add_argument("--max-unknowns", type=int, default=0)
    pr.add_argument("--max-findings", type=int, default=0)
    pr.add_argument("--max-run-age-days", type=int, default=30)
    pr.add_argument("--require-pass", action="store_true",
                    help="exit 1 if the gate verdict is not pass")


def _candidate_runs(world: ArchitectureWorld) -> list[str]:
    """All runs that begin with the proposal- prefix in this project."""
    out: list[str] = []
    for run_id in world.list_runs():
        if run_id.startswith(PROPOSAL_PREFIX):
            out.append(run_id)
    return out


def _candidate_status(world: ArchitectureWorld, run_id: str) -> str:
    """Best-effort status: approved > rejected > open.

    Best-effort because the proposal object may live in a fork
    that has since been deleted; in that case the candidate is
    effectively open (no decision recorded)."""
    try:
        fork = world.view(run_id)
    except (KeyError, RuntimeError) as exc:
        print(f"warning: cannot inspect candidate '{run_id}':"
              f" {exc}", file=sys.stderr)
        return "open"
    try:
        for obj in fork.find_objects("proposal"):
            data = obj.get("data") or {}
            status = data.get("status")
            if status in ("approved", "rejected"):
                return status
    finally:
        fork.close()
    return "open"


def handle_list(args: argparse.Namespace, world: ArchitectureWorld) -> int:
    if not world.db_path.exists():
        print(f"error: no Architecture World for {world.project_id}",
              file=sys.stderr)
        return 1
    rows = []
    for run_id in sorted(_candidate_runs(world)):
        name = run_id.removeprefix(PROPOSAL_PREFIX)
        rows.append({"name": name, "run_id": run_id,
                     "status": _candidate_status(world, run_id)})
    print(json.dumps({"schema": "arch-skillkit/proposals-list-v1",
                      "project_id": world.project_id,
                      "candidates": rows}, indent=2))
    return 0


def handle_review(args: argparse.Namespace,
                  world: ArchitectureWorld) -> int:
    if not world.db_path.exists():
        print(f"error: no Architecture World for {world.project_id}",
              file=sys.stderr)
        return 1
    name = args.name
    run_id = f"{PROPOSAL_PREFIX}{name}"
    if not world.has_run(run_id):
        print(f"error: no candidate '{name}' (run: archskillkit fork "
              f"--repo {world.root or '.'} --name {name})",
              file=sys.stderr)
        return 1

    with world:
        fork = world.view(run_id)
        diff = structural_diff(world, fork)
        # The gate is evaluated against the FORK view of the world:
        # a candidate can only be promoted if, after merge, the gate
        # would still pass against that snapshot.
        index_path = fork.workspace / "code.sqlite"
        index = (CodeIndex(index_path).open()
                 if index_path.exists() else None)
        try:
            snapshot = build_snapshot(fork, code_index=index)
            thresholds = FitnessThresholds(
                min_evidence_coverage=args.min_coverage,
                max_unknowns=args.max_unknowns,
                max_findings=args.max_findings,
                max_run_age_days=args.max_run_age_days,
            )
            result = evaluate_gate(fork, snapshot,
                                   thresholds=thresholds,
                                   ledger=RunLedger(),
                                   waivers=WaiverLedger())
        finally:
            if index is not None:
                index.close()

    diff_dict = {k: v for k, v in vars(diff).items()}
    diff_dict["is_empty"] = diff.is_empty()

    envelope = {
        "schema": "arch-skillkit/proposal-review-v1",
        "candidate": name,
        "run_id": run_id,
        "structural_diff": diff_dict,
        "gate": json.loads(render_json(result)),
    }
    print(json.dumps(envelope, indent=2))
    if args.require_pass and result.verdict != "pass":
        return 1
    return 0


def handle(args: argparse.Namespace, world: ArchitectureWorld) -> int:
    if args.proposals_action == "list":
        return handle_list(args, world)
    if args.proposals_action == "review":
        return handle_review(args, world)
    print(f"error: unknown proposals action: {args.proposals_action!r}",
          file=sys.stderr)
    return 2
