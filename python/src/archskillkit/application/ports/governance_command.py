"""Governance command port (V2.5 M1, ADR-0046/0047).

This is the write side of the governance CQRS boundary.
Inbound adapters (CLI, MCP, HTTP) issue commands through this port;
the application layer executes them and returns typed result envelopes.
"""

from __future__ import annotations

from typing import Protocol, TypeVar

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

CommandResult = (
    ProposalListResult
    | ProposalCreateResult
    | ProposalDiffResult
    | ProposalReviewResult
    | ProposalPromoteResult
    | ProposalRejectResult
    | CommandError
)

T = TypeVar("T")


class GovernanceCommandPort(Protocol):
    """Execute governance commands against a repository.

    Each method corresponds to one step in the candidate workflow.
    Results are schema-bound envelopes; errors carry a stable code.
    """

    def list_proposals(self) -> ProposalListResult:
        """List all proposal-* runs in the world."""
        ...

    def create_proposal(self, command: ProposalCreateCommand) -> ProposalCreateResult | CommandError:
        """Fork the base world into a candidate run."""
        ...

    def diff_proposal(self, command: ProposalDiffCommand) -> ProposalDiffResult | CommandError:
        """Structural diff between base and candidate."""
        ...

    def review_proposal(self, command: ProposalReviewCommand) -> ProposalReviewResult | CommandError:
        """Evaluate fitness gate + structural diff against the candidate."""
        ...

    def promote_proposal(
        self, command: ProposalPromoteCommand
    ) -> ProposalPromoteResult | CommandError:
        """Promote a candidate to base; records approval first."""
        ...

    def reject_proposal(self, command: ProposalRejectCommand) -> ProposalRejectResult | CommandError:
        """Mark a candidate as rejected; does not mutate base."""
        ...
