"""`archskillkit proposals` — candidate workflow (V2.4 M4, docs/v2/59).

The candidate -> review -> promote path:

  create  ->  diff  ->  review  ->  promote  (or reject)

  archskillkit proposals create   --repo PATH --name NAME   fork base world
  archskillkit proposals list     --repo PATH               list candidates
  archskillkit proposals diff     --repo PATH --name NAME   structural diff
  archskillkit proposals review   --repo PATH --name NAME   fitness gate +
                                                            structural diff
  archskillkit proposals promote  --repo PATH --name NAME --approved-by WHO
  archskillkit proposals reject   --repo PATH --name NAME --actor WHO

Every action returns a schema-bound JSON envelope. The MCP delivery
adapter (delivery/cli/mcp.py) delegates to these helpers so wire
calls reuse exactly the same logic and envelopes as the CLI.
"""

from __future__ import annotations

import argparse
import json
import sys

from archskillkit.application.commands.governance import GovernanceApplicationService
from archskillkit.application.models.governance import (
    ProposalCreateCommand,
    ProposalDiffCommand,
    ProposalPromoteCommand,
    ProposalRejectCommand,
    ProposalReviewCommand,
)
from archskillkit.world import ArchitectureWorld

NAME = "proposals"
NEEDS_WORLD = True
PROPOSAL_PREFIX = "proposal-"

SCHEMA_LIST = "arch-skillkit/proposals-list-v1"
SCHEMA_CREATE = "arch-skillkit/proposal-create-v1"
SCHEMA_DIFF = "arch-skillkit/proposal-diff-v1"
SCHEMA_REVIEW = "arch-skillkit/proposal-review-v1"
SCHEMA_PROMOTE = "arch-skillkit/proposal-promote-v1"
SCHEMA_REJECT = "arch-skillkit/proposal-reject-v1"


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(NAME, help="candidate -> review -> promote workflow")
    p.add_argument("--repo", required=True)
    sub = p.add_subparsers(dest="proposals_action", required=True)
    sub.add_parser("list", help="list candidate (proposal-*) runs")
    pc = sub.add_parser(
        "create", help="fork the base world into a candidate (alias of `archskillkit fork`)"
    )
    pc.add_argument("--name", required=True)
    pc.add_argument(
        "--prompt-spec",
        default=None,
        help="PromptSpec name to record for provenance (e.g. architecture-analyst). Optional.",
    )
    pc.add_argument(
        "--skill",
        action="append",
        default=[],
        help="Skill name the agent was operating under (repeatable). "
        "Optional; records content-addressed revisions.",
    )
    pd = sub.add_parser("diff", help="structural diff between base and the candidate")
    pd.add_argument("--name", required=True)
    pr = sub.add_parser(
        "review", help="review a candidate against the fitness gate + structural diff"
    )
    pr.add_argument("--name", required=True)
    pr.add_argument("--min-coverage", type=float, default=0.8)
    pr.add_argument("--max-unknowns", type=int, default=0)
    pr.add_argument("--max-findings", type=int, default=0)
    pr.add_argument("--max-run-age-days", type=int, default=30)
    pr.add_argument(
        "--require-pass", action="store_true", help="exit 1 if the gate verdict is not pass"
    )
    pp = sub.add_parser("promote", help="promote a candidate to base")
    pp.add_argument("--name", required=True)
    pp.add_argument("--approved-by", required=True)
    pj = sub.add_parser("reject", help="mark a candidate as rejected")
    pj.add_argument("--name", required=True)
    pj.add_argument("--actor", required=True)


# ---------- shared helpers ----------


def _require_candidate(world: ArchitectureWorld, name: str) -> tuple[str | None, dict | None]:
    """Return (run_id, error_envelope). Exactly one is None."""
    run_id = f"{PROPOSAL_PREFIX}{name}"
    if not world.has_run(run_id):
        return None, {
            "error": "CANDIDATE_NOT_FOUND",
            "message": f"no candidate '{name}' (run: archskillkit proposals create --name {name})",
            "name": name,
            "run_id": run_id,
        }
    return run_id, None


# ---------- actions ----------


def handle_list(args: argparse.Namespace, world: ArchitectureWorld) -> int:
    """List all proposal-* runs in the world."""

    service = GovernanceApplicationService(world)
    result = service.list_proposals()
    print(json.dumps(result.model_dump(), indent=2))
    return 0


def handle_create(args: argparse.Namespace, world: ArchitectureWorld) -> int:
    """Fork the base world into a candidate run."""

    prompt_name = getattr(args, "prompt_spec", None) or None
    skill_names = list(getattr(args, "skill", []) or [])
    cmd = ProposalCreateCommand(name=args.name, prompt_spec=prompt_name, skills=skill_names)

    service = GovernanceApplicationService(world)
    result = service.create_proposal(cmd)
    if hasattr(result, "error"):
        err = result
        print(json.dumps(err.model_dump()), file=sys.stderr)
        return 1
    print(json.dumps(result.model_dump(), indent=2))
    return 0


def handle_diff(args: argparse.Namespace, world: ArchitectureWorld) -> int:
    """Return the structural diff between base and the candidate."""

    service = GovernanceApplicationService(world)
    cmd = ProposalDiffCommand(name=args.name)
    result = service.diff_proposal(cmd)
    if hasattr(result, "error"):
        err = result
        print(json.dumps(err.model_dump()), file=sys.stderr)
        return 1
    print(json.dumps(result.model_dump(), indent=2))
    return 0


def handle_review(args: argparse.Namespace, world: ArchitectureWorld) -> int:
    """Evaluate fitness gate + structural diff against the candidate."""
    from archskillkit.codeindex import CodeIndex

    service = GovernanceApplicationService(world)
    cmd = ProposalReviewCommand(
        name=args.name,
        min_coverage=args.min_coverage,
        max_unknowns=args.max_unknowns,
        max_findings=args.max_findings,
        max_run_age_days=args.max_run_age_days,
        require_pass=args.require_pass,
    )
    # Delivery layer opens the CodeIndex (ARC-005: application must not).
    fork_run = f"proposal-{args.name}"
    index = None
    if world.has_run(fork_run):
        with world:
            fork = world.view(fork_run)
            index_path = fork.workspace / "code.sqlite"
            index = CodeIndex(index_path).open() if index_path.exists() else None
    try:
        result = service.review_proposal(cmd, index=index)
    finally:
        if index is not None:
            index.close()
    if hasattr(result, "error"):
        err = result
        print(json.dumps(err.model_dump()), file=sys.stderr)
        return 1
    print(json.dumps(result.model_dump(), indent=2))
    # require_pass is handled inside the service (exit 1 on fail verdict)
    return 0


def handle_promote(args: argparse.Namespace, world: ArchitectureWorld) -> int:
    """Promote a candidate to base; records approval first."""

    service = GovernanceApplicationService(world)
    cmd = ProposalPromoteCommand(name=args.name, approved_by=args.approved_by)
    result = service.promote_proposal(cmd)
    if hasattr(result, "error"):
        err = result
        print(json.dumps(err.model_dump()), file=sys.stderr)
        return 1
    print(json.dumps(result.model_dump(), indent=2))
    return 0


def handle_reject(args: argparse.Namespace, world: ArchitectureWorld) -> int:
    """Mark a candidate as rejected; does not mutate base."""

    service = GovernanceApplicationService(world)
    cmd = ProposalRejectCommand(name=args.name, actor=args.actor)
    result = service.reject_proposal(cmd)
    if hasattr(result, "error"):
        err = result
        print(json.dumps(err.model_dump()), file=sys.stderr)
        return 1
    print(json.dumps(result.model_dump(), indent=2))
    return 0


def handle(args: argparse.Namespace, world: ArchitectureWorld) -> int:
    action = args.proposals_action
    if action == "list":
        return handle_list(args, world)
    if action == "create":
        return handle_create(args, world)
    if action == "diff":
        return handle_diff(args, world)
    if action == "review":
        return handle_review(args, world)
    if action == "promote":
        return handle_promote(args, world)
    if action == "reject":
        return handle_reject(args, world)
    print(f"error: unknown proposals action: {action!r}", file=sys.stderr)
    return 2
