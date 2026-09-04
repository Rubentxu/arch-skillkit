"""Governance command DTOs (V2.5 M1, ADR-0046/0047).

These DTOs carry the typed inputs/outputs for the governance
candidate workflow: list / create / diff / review / promote / reject.

Inbound adapters (CLI, MCP, HTTP) parse their inputs into these DTOs,
call the application command handlers, and render the results.
No adapter calls another adapter's handlers directly.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ProposalCreateCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Candidate run name (without the proposal- prefix)")
    prompt_spec: str | None = Field(
        default=None,
        description="PromptSpec name to record for provenance (e.g. architecture-analyst)",
    )
    skills: list[str] = Field(
        default_factory=list,
        description="Skill names the agent was operating under (repeatable)",
    )


class ProposalDiffCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Candidate run name")


class ProposalReviewCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Candidate run name")
    min_coverage: float = Field(default=0.8, description="Minimum evidence coverage threshold")
    max_unknowns: int = Field(default=0, description="Maximum acceptable unknown count")
    max_findings: int = Field(default=0, description="Maximum acceptable findings count")
    max_run_age_days: int = Field(default=30, description="Maximum run age in days")
    require_pass: bool = Field(
        default=False,
        description="Return error exit code if gate verdict is not pass",
    )


class ProposalPromoteCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Candidate run name")
    approved_by: str = Field(description="Human actor approving the promotion")


class ProposalRejectCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Candidate run name")
    actor: str = Field(description="Human actor recording the rejection")


# ---------- result envelopes ----------


class ProposalMetadataResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    prompt_spec_name: str
    prompt_spec_version: str
    prompt_spec_hash: str
    skill_count: int


class ProposalListResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema: str = "arch-skillkit/proposals-list-v1"
    project_id: str
    candidates: list[dict] = Field(default_factory=list)


class ProposalCreateResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema: str = "arch-skillkit/proposal-create-v1"
    name: str
    run_id: str
    project_id: str
    metadata: dict | None = None


class ProposalDiffResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema: str = "arch-skillkit/proposal-diff-v1"
    name: str
    run_id: str
    structural_diff: dict


class ProposalReviewResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema: str = "arch-skillkit/proposal-review-v1"
    candidate: str
    run_id: str
    structural_diff: dict
    gate: dict
    metadata: dict | None = None


class ProposalPromoteResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema: str = "arch-skillkit/proposal-promote-v1"
    promoted_run_id: str
    base_snapshot_id: str
    promoted_snapshot_id: str
    elements_added: int = 0
    relations_added: int = 0
    elements_removed: int = 0
    relations_removed: int = 0


class ProposalRejectResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema: str = "arch-skillkit/proposal-reject-v1"
    name: str
    run_id: str
    actor: str
    status: Literal["rejected"] = "rejected"


class CommandError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: str
    message: str
    name: str | None = None
    run_id: str | None = None
    skill: str | None = None
