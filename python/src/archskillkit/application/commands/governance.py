"""Governance command service (V2.5 M1, ADR-0046/0047).

Implements the GovernanceCommandPort using domain objects and outbound ports.
This is the canonical application-layer implementation of the proposal workflow.

Candidates flow: create -> diff -> review -> promote | reject

All adapters (CLI, MCP, HTTP) issue commands through this service.
No adapter calls another adapter's handlers directly.
"""

from __future__ import annotations

import json
from pathlib import Path

from archskillkit.agent_governance import (
    ProposalMetadata,
    get_proposal_metadata,
    record_proposal_metadata,
)
from archskillkit.application.models.governance import (
    CommandError,
    ProposalCreateCommand,
    ProposalCreateResult,
    ProposalDiffCommand,
    ProposalDiffResult,
    ProposalListResult,
    ProposalPromoteCommand,
    ProposalPromoteResult,
    ProposalRejectCommand,
    ProposalRejectResult,
    ProposalReviewCommand,
    ProposalReviewResult,
)
from archskillkit.application.ports.governance_command import GovernanceCommandPort
from archskillkit.application.queries.fitness import FitnessThresholds, evaluate_gate
from archskillkit.application.queries.report import render_json
from archskillkit.application.snapshot_builder import build_snapshot
from archskillkit.proposals import PromotionError, promote, structural_diff
from archskillkit.runtime_state.run_ledger import RunLedger
from archskillkit.runtime_state.waivers import WaiverLedger
from archskillkit.ports import ArchitectureWorldPort

PROPOSAL_PREFIX = "proposal-"


def _require_main_world(world: ArchitectureWorldPort) -> CommandError | None:
    if not world.db_path.exists():
        return CommandError(
            error="BASE_WORLD_MISSING",
            message=f"no Architecture World for {world.project_id}"
            f" (run: archskillkit discover --repo {world.root or '.'})",
        )
    return None


def _require_candidate(world: ArchitectureWorldPort, name: str) -> tuple[str, None] | tuple[None, CommandError]:
    run_id = f"{PROPOSAL_PREFIX}{name}"
    if not world.has_run(run_id):
        return None, CommandError(
            error="CANDIDATE_NOT_FOUND",
            message=f"no candidate '{name}' (run: archskillkit proposals create --name {name})",
            name=name,
            run_id=run_id,
        )
    return run_id, None


def _candidate_runs(world: ArchitectureWorldPort) -> list[str]:
    return [rid for rid in world.list_runs() if rid.startswith(PROPOSAL_PREFIX)]


def _candidate_status(world: ArchitectureWorldPort, run_id: str) -> str:
    try:
        fork = world.view(run_id)
    except (KeyError, RuntimeError):
        return "open"
    try:
        for obj in fork.find_objects("proposal"):
            status = (obj.get("data") or {}).get("status")
            if status in ("approved", "rejected"):
                return status
    finally:
        fork.close()
    return "open"


class GovernanceApplicationService:
    """Canonical application-layer implementation of the governance workflow.

    Implements GovernanceCommandPort. All inbound adapters delegate here.
    """

    def __init__(self, world: ArchitectureWorldPort) -> None:
        self._world = world

    def list_proposals(self) -> ProposalListResult:
        err = _require_main_world(self._world)
        if err is not None:
            # Caller is responsible for printing the error; this path
            # is used by CLI which handles errors via exit codes.
            return ProposalListResult(schema="arch-skillkit/proposals-list-v1", project_id="", candidates=[])

        rows = []
        for run_id in sorted(_candidate_runs(self._world)):
            name = run_id.removeprefix(PROPOSAL_PREFIX)
            status = _candidate_status(self._world, run_id)
            metadata = get_proposal_metadata(self._world, run_id)
            row: dict = {"name": name, "run_id": run_id, "status": status}
            if metadata is not None:
                row["metadata"] = {
                    "prompt_spec_name": metadata.prompt_spec_name,
                    "prompt_spec_version": metadata.prompt_spec_version,
                    "prompt_spec_hash": metadata.prompt_spec_hash,
                    "skill_count": len(metadata.skill_revisions),
                }
            rows.append(row)

        return ProposalListResult(
            schema="arch-skillkit/proposals-list-v1",
            project_id=self._world.project_id,
            candidates=rows,
        )

    def create_proposal(self, command: ProposalCreateCommand) -> ProposalCreateResult | CommandError:
        err = _require_main_world(self._world)
        if err is not None:
            return err

        metadata: ProposalMetadata | None = None
        # Resolve provenance metadata if provided
        if command.prompt_spec or command.skills:
            from archskillkit.agent_governance import find_skill_revision, get_prompt_spec

            try:
                if command.prompt_spec:
                    spec = get_prompt_spec(command.prompt_spec)
                    prompt_version = spec.version
                    prompt_hash = spec.digest()
                else:
                    prompt_version = ""
                    prompt_hash = ""
            except KeyError as exc:
                return CommandError(error="METADATA_INVALID", message=str(exc))

            skill_revisions = []
            skills_root = Path.home() / ".config" / "opencode" / "skills"
            for skill_name in command.skills:
                revision = find_skill_revision(skill_name, skills_root)
                if revision is None:
                    return CommandError(
                        error="METADATA_INVALID",
                        message=f"skill {skill_name!r} is not versioned; add a 'version:' line to its SKILL.md",
                        skill=skill_name,
                    )
                skill_revisions.append(revision)

            metadata = ProposalMetadata(
                prompt_spec_name=command.prompt_spec or "",
                prompt_spec_version=prompt_version,
                prompt_spec_hash=prompt_hash,
                skill_revisions=skill_revisions,
            )

        with self._world:
            fork = self._world.fork(command.name)
            if metadata is not None:
                record_proposal_metadata(self._world, fork.run_id, metadata)

        envelope: dict = {
            "name": command.name,
            "run_id": fork.run_id,
            "project_id": self._world.project_id,
        }
        if metadata is not None:
            envelope["metadata"] = metadata.to_object()

        return ProposalCreateResult(
            schema="arch-skillkit/proposal-create-v1",
            name=command.name,
            run_id=fork.run_id,
            project_id=self._world.project_id,
            metadata=envelope.get("metadata"),
        )

    def diff_proposal(self, command: ProposalDiffCommand) -> ProposalDiffResult | CommandError:
        err = _require_main_world(self._world)
        if err is not None:
            return err

        run_id, err = _require_candidate(self._world, command.name)
        if err is not None:
            return err

        with self._world:
            fork = self._world.view(run_id)
            diff = structural_diff(self._world, fork)

        diff_dict = {k: v for k, v in vars(diff).items()}
        diff_dict["is_empty"] = diff.is_empty()

        return ProposalDiffResult(
            schema="arch-skillkit/proposal-diff-v1",
            name=command.name,
            run_id=run_id,
            structural_diff=diff_dict,
        )

    def review_proposal(
        self, command: ProposalReviewCommand, index=None
    ) -> ProposalReviewResult | CommandError:
        """Evaluate a proposal against fitness thresholds.

        The ``index`` parameter is optional. When provided it must be an open
        CodeIndex instance opened by the delivery layer (ARC-005: application
        must not instantiate CodeIndex). When None, build_snapshot will report
        INDEX_MISSING in the gate result.
        """
        err = _require_main_world(self._world)
        if err is not None:
            return err

        run_id, err = _require_candidate(self._world, command.name)
        if err is not None:
            return err

        with self._world:
            fork = self._world.view(run_id)
            diff = structural_diff(self._world, fork)
            snapshot = build_snapshot(fork, code_index=index)
            thresholds = FitnessThresholds(
                min_evidence_coverage=command.min_coverage,
                max_unknowns=command.max_unknowns,
                max_findings=command.max_findings,
                max_run_age_days=command.max_run_age_days,
            )
            result = evaluate_gate(
                fork, snapshot, thresholds=thresholds, ledger=RunLedger(), waivers=WaiverLedger()
            )

        diff_dict = {k: v for k, v in vars(diff).items()}
        diff_dict["is_empty"] = diff.is_empty()
        metadata = get_proposal_metadata(self._world, run_id)

        return ProposalReviewResult(
            schema="arch-skillkit/proposal-review-v1",
            candidate=command.name,
            run_id=run_id,
            structural_diff=diff_dict,
            gate=json.loads(render_json(result)),
            metadata=metadata.to_object() if metadata else None,
        )

    def promote_proposal(
        self, command: ProposalPromoteCommand
    ) -> ProposalPromoteResult | CommandError:
        err = _require_main_world(self._world)
        if err is not None:
            return err

        run_id, err = _require_candidate(self._world, command.name)
        if err is not None:
            return err

        with self._world:
            fork = self._world.view(run_id)
            fork.record_proposal(command.name)
            try:
                fork.approve_proposal(command.name, actor=command.approved_by)
                summary = promote(self._world, fork)
            except PromotionError as exc:
                return CommandError(error="PROMOTION_FAILED", message=str(exc), name=command.name, run_id=run_id)

        return ProposalPromoteResult(
            schema="arch-skillkit/proposal-promote-v1",
            promoted_run_id=run_id,
            base_snapshot_id=summary.get("base_snapshot_id", ""),
            promoted_snapshot_id=summary.get("promoted_snapshot_id", ""),
            elements_added=summary.get("elements_added", 0),
            relations_added=summary.get("relations_added", 0),
            elements_removed=summary.get("elements_removed", 0),
            relations_removed=summary.get("relations_removed", 0),
        )

    def reject_proposal(self, command: ProposalRejectCommand) -> ProposalRejectResult | CommandError:
        err = _require_main_world(self._world)
        if err is not None:
            return err

        run_id, err = _require_candidate(self._world, command.name)
        if err is not None:
            return err

        with self._world:
            fork = self._world.view(run_id)
            fork.record_proposal(command.name)
            try:
                fork.reject_proposal(command.name, actor=command.actor)
            except PromotionError as exc:
                return CommandError(
                    error="REJECTION_FAILED", message=str(exc), name=command.name, run_id=run_id
                )

        return ProposalRejectResult(
            schema="arch-skillkit/proposal-reject-v1",
            name=command.name,
            run_id=run_id,
            actor=command.actor,
            status="rejected",
        )
