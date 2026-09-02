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
from pathlib import Path

from archskillkit.agent_governance import (
    ProposalMetadata,
    SkillRevision,
    find_skill_revision,
    get_prompt_spec,
    get_proposal_metadata,
    record_proposal_metadata,
)
from archskillkit.application.queries.fitness import (
    FitnessThresholds,
    evaluate_gate,
)
from archskillkit.application.queries.report import render_json
from archskillkit.application.snapshot_builder import build_snapshot
from archskillkit.codeindex import CodeIndex
from archskillkit.proposals import (
    PromotionError,
    promote,
    structural_diff,
)
from archskillkit.runtime_state.run_ledger import RunLedger
from archskillkit.runtime_state.waivers import WaiverLedger
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


def _default_skills_root() -> Path:
    """Resolve the skills root from env, then from the well-known
    install location, then from the local `skills/` directory next
    to the arch-skillkit package.

    MCP and CLI processes share this default so a candidate
    produced via MCP carries the same skill revisions as one
    produced via the CLI."""
    import os

    env = os.environ.get("ARCH_SKILLKIT_SKILLS_ROOT")
    if env:
        return Path(env)
    # Local repo: <arch-skillkit>/skills.
    repo_root = Path(__file__).resolve().parents[4]
    return repo_root / "skills"


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
        print(f"warning: cannot inspect candidate '{run_id}': {exc}", file=sys.stderr)
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


def _require_main_world(world: ArchitectureWorld) -> dict | None:
    """Return a base-world-missing error envelope or None."""
    if not world.db_path.exists():
        return {
            "error": "BASE_WORLD_MISSING",
            "message": f"no Architecture World for {world.project_id}"
            f" (run: archskillkit discover --repo"
            f" {world.root or '.'})",
        }
    return None


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


class ProposalMetadataError(Exception):
    """Raised when a caller asks to record provenance but the
    inputs cannot be resolved (unknown prompt spec, unversioned
    skill, etc). Carries a stable error code so the MCP wire
    layer surfaces it without parsing free-form text."""

    code = "METADATA_INVALID"

    def __init__(self, message: str, **details) -> None:
        super().__init__(message)
        self.message = message
        self.details = dict(details)

    def to_envelope(self) -> dict:
        return {"error": self.code, "message": self.message, **self.details}


def _resolve_metadata(
    world: ArchitectureWorld, name: str, prompt_name: str | None, skill_names: list[str]
) -> ProposalMetadata:
    """Resolve a ProposalMetadata from CLI/MCP inputs.

    Raises ProposalMetadataError if any input cannot be resolved
    to a known, versioned, content-addressed reference."""
    if not prompt_name:
        raise ProposalMetadataError(
            "metadata requires --prompt-spec (the candidate's "
            "embedded agent must declare its prompt)"
        )
    try:
        spec = get_prompt_spec(prompt_name)
    except KeyError as exc:
        raise ProposalMetadataError(str(exc), prompt_spec=prompt_name)
    skill_revisions: list[SkillRevision] = []
    skills_root = _default_skills_root()
    for skill_name in skill_names:
        revision = find_skill_revision(skill_name, skills_root)
        if revision is None:
            raise ProposalMetadataError(
                f"skill {skill_name!r} is not versioned in"
                f" {skills_root}; add a 'version:' line to its"
                f" SKILL.md frontmatter",
                skill=skill_name,
                skills_root=str(skills_root),
            )
        skill_revisions.append(revision)
    return ProposalMetadata(
        prompt_spec_name=spec.name,
        prompt_spec_version=spec.version,
        prompt_spec_hash=spec.digest(),
        skill_revisions=skill_revisions,
    )


# ---------- actions ----------


def handle_list(args: argparse.Namespace, world: ArchitectureWorld) -> int:
    err = _require_main_world(world)
    if err is not None:
        print(json.dumps(err), file=sys.stderr)
        return 1
    rows = []
    for run_id in sorted(_candidate_runs(world)):
        name = run_id.removeprefix(PROPOSAL_PREFIX)
        status = _candidate_status(world, run_id)
        metadata = get_proposal_metadata(world, run_id)
        row = {"name": name, "run_id": run_id, "status": status}
        if metadata is not None:
            row["metadata"] = {
                "prompt_spec_name": metadata.prompt_spec_name,
                "prompt_spec_version": metadata.prompt_spec_version,
                "prompt_spec_hash": metadata.prompt_spec_hash,
                "skill_count": len(metadata.skill_revisions),
            }
        rows.append(row)
    envelope = {"schema": SCHEMA_LIST, "project_id": world.project_id, "candidates": rows}
    print(json.dumps(envelope, indent=2))
    return 0


def handle_create(args: argparse.Namespace, world: ArchitectureWorld) -> int:
    """Fork the base world into a candidate run.

    When the caller passes --prompt-spec and/or --skill, record
    the provenance metadata (prompt spec name+version+hash, skill
    name+version+content hash) into the fork so a later review
    can answer "what produced this candidate?"."""
    err = _require_main_world(world)
    if err is not None:
        print(json.dumps(err), file=sys.stderr)
        return 1
    name = args.name
    metadata: ProposalMetadata | None = None
    metadata_error: dict | None = None
    prompt_name = getattr(args, "prompt_spec", None)
    skill_names = list(getattr(args, "skill", []) or [])
    if prompt_name or skill_names:
        try:
            metadata = _resolve_metadata(world, name, prompt_name, skill_names)
        except ProposalMetadataError as exc:
            metadata_error = exc.to_envelope()
            # Bail out: we will NOT create the fork if provenance
            # cannot be resolved. The caller must fix the inputs.
            print(json.dumps(metadata_error), file=sys.stderr)
            return 1
    # Fork first (one transaction: copies events into the new run).
    with world:
        fork = world.fork(name)
        # Record metadata inside the same world transaction so the
        # writes commit atomically with the fork itself. A second
        # transaction outside `with world:` would risk a stale read
        # from a freshly-opened sqlite handle.
        if metadata is not None:
            record_proposal_metadata(world, fork.run_id, metadata)
    envelope = {
        "schema": SCHEMA_CREATE,
        "name": name,
        "run_id": fork.run_id,
        "project_id": world.project_id,
    }
    if metadata is not None:
        envelope["metadata"] = metadata.to_object()
    print(json.dumps(envelope, indent=2))
    return 0


def handle_diff(args: argparse.Namespace, world: ArchitectureWorld) -> int:
    """Return the structural diff between base and the candidate."""
    err = _require_main_world(world)
    if err is not None:
        print(json.dumps(err), file=sys.stderr)
        return 1
    run_id, err = _require_candidate(world, args.name)
    if err is not None:
        print(json.dumps(err), file=sys.stderr)
        return 1
    with world:
        fork = world.view(run_id)
        diff = structural_diff(world, fork)
    diff_dict = {k: v for k, v in vars(diff).items()}
    diff_dict["is_empty"] = diff.is_empty()
    envelope = {
        "schema": SCHEMA_DIFF,
        "name": args.name,
        "run_id": run_id,
        "structural_diff": diff_dict,
    }
    print(json.dumps(envelope, indent=2))
    return 0


def handle_review(args: argparse.Namespace, world: ArchitectureWorld) -> int:
    """Evaluate fitness gate + structural diff against the candidate."""
    err = _require_main_world(world)
    if err is not None:
        print(json.dumps(err), file=sys.stderr)
        return 1
    run_id, err = _require_candidate(world, args.name)
    if err is not None:
        print(json.dumps(err), file=sys.stderr)
        return 1

    with world:
        fork = world.view(run_id)
        diff = structural_diff(world, fork)
        index_path = fork.workspace / "code.sqlite"
        index = CodeIndex(index_path).open() if index_path.exists() else None
        try:
            snapshot = build_snapshot(fork, code_index=index)
            thresholds = FitnessThresholds(
                min_evidence_coverage=args.min_coverage,
                max_unknowns=args.max_unknowns,
                max_findings=args.max_findings,
                max_run_age_days=args.max_run_age_days,
            )
            result = evaluate_gate(
                fork, snapshot, thresholds=thresholds, ledger=RunLedger(), waivers=WaiverLedger()
            )
        finally:
            if index is not None:
                index.close()

    diff_dict = {k: v for k, v in vars(diff).items()}
    diff_dict["is_empty"] = diff.is_empty()

    metadata = get_proposal_metadata(world, run_id)

    envelope = {
        "schema": SCHEMA_REVIEW,
        "candidate": args.name,
        "run_id": run_id,
        "structural_diff": diff_dict,
        "gate": json.loads(render_json(result)),
    }
    if metadata is not None:
        envelope["metadata"] = metadata.to_object()
    print(json.dumps(envelope, indent=2))
    if args.require_pass and result.verdict != "pass":
        return 1
    return 0


def handle_promote(args: argparse.Namespace, world: ArchitectureWorld) -> int:
    """Promote a candidate to base; records approval first."""
    err = _require_main_world(world)
    if err is not None:
        print(json.dumps(err), file=sys.stderr)
        return 1
    name = args.name
    run_id, err = _require_candidate(world, name)
    if err is not None:
        print(json.dumps(err), file=sys.stderr)
        return 1
    with world:
        fork = world.view(run_id)
        fork.record_proposal(name)
        try:
            fork.approve_proposal(name, actor=args.approved_by)
            summary = promote(world, fork)
        except PromotionError as exc:
            err = {"error": "PROMOTION_FAILED", "message": str(exc), "name": name, "run_id": run_id}
            print(json.dumps(err), file=sys.stderr)
            return 1
    envelope = {"schema": SCHEMA_PROMOTE, **summary}
    print(json.dumps(envelope, indent=2))
    return 0


def handle_reject(args: argparse.Namespace, world: ArchitectureWorld) -> int:
    """Mark a candidate as rejected; does not mutate base."""
    err = _require_main_world(world)
    if err is not None:
        print(json.dumps(err), file=sys.stderr)
        return 1
    name = args.name
    run_id, err = _require_candidate(world, name)
    if err is not None:
        print(json.dumps(err), file=sys.stderr)
        return 1
    with world:
        fork = world.view(run_id)
        fork.record_proposal(name)
        try:
            fork.reject_proposal(name, actor=args.actor)
        except PromotionError as exc:
            err = {"error": "REJECTION_FAILED", "message": str(exc), "name": name, "run_id": run_id}
            print(json.dumps(err), file=sys.stderr)
            return 1
    envelope = {
        "schema": SCHEMA_REJECT,
        "name": name,
        "run_id": run_id,
        "actor": args.actor,
        "status": "rejected",
    }
    print(json.dumps(envelope, indent=2))
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
