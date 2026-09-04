"""Bootstrap: ArchSkillKitApplication Composition Root (V2.5 M2, ADR-0046).

This module is the single authority for constructing the runtime for a repository.
No inbound adapter should call ``ArchitectureWorld.for_repo(...)`` or
``CodeIndex(...)`` directly.

Usage::

    app = ArchSkillKitApplication.for_repo("/path/to/repo")
    app.open()
    try:
        result = app.status()
        # ...
    finally:
        app.close()

Or as a context manager::

    with ArchSkillKitApplication.for_repo("/path/to/repo") as app:
        result = app.status()
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from archskillkit.codeindex import CodeIndex
    from archskillkit.world import ArchitectureWorld


class ArchSkillKitApplication:
    """Composition Root: single authority for world + index lifecycle.

    Adapters (CLI, MCP, HTTP) MUST NOT construct ArchitectureWorld or
    CodeIndex directly. They receive an app instance from this factory
    and call its methods.
    """

    def __init__(self, repo_path: Path) -> None:
        self._repo_path = repo_path
        self._world: ArchitectureWorld | None = None
        self._index: CodeIndex | None = None
        self._opened = False

    # -- lifecycle ---------------------------------------------------------

    def open(self) -> ArchSkillKitApplication:
        """Open the world and code index for this repository.

        Sets ``world._arch_app = self`` so handlers that receive the world
        can access ``app.index`` and call app methods without managing
        their own lifecycle (M3 slice 3).
        """
        if self._opened:
            return self
        from archskillkit.codeindex import CodeIndex
        from archskillkit.world import ArchitectureWorld

        self._world = ArchitectureWorld.for_repo(self._repo_path).open()
        index_path = self._world.workspace / "code.sqlite"
        self._index = CodeIndex(index_path).open() if index_path.exists() else None
        # Reverse reference so handlers can reach app.index from world._arch_app
        self._world._arch_app = self
        self._opened = True
        return self

    def close(self) -> None:
        """Close the world and index, releasing resources."""
        if self._index is not None:
            self._index.close()
            self._index = None
        if self._world is not None:
            self._world.close()
            self._world = None
        self._opened = False

    def __enter__(self) -> ArchSkillKitApplication:
        return self.open()

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    @classmethod
    def for_repo(cls, repo_path: str | Path) -> ArchSkillKitApplication:
        """Create an app instance for the given repository path."""
        return cls(Path(repo_path))

    # -- accessors ---------------------------------------------------------

    @property
    def world(self) -> ArchitectureWorld:
        if not self._opened or self._world is None:
            raise RuntimeError("Application not open. Call .open() first.")
        return self._world

    @property
    def index(self) -> CodeIndex | None:
        if not self._opened:
            raise RuntimeError("Application not open. Call .open() first.")
        return self._index

    @property
    def is_open(self) -> bool:
        return self._opened

    # -- governance commands (M1) -------------------------------------------

    def list_proposals(self):
        """List all proposal runs."""
        from archskillkit.application.commands.governance import GovernanceApplicationService

        service = GovernanceApplicationService(self.world)
        return service.list_proposals()

    def create_proposal(self, command):
        """Create a proposal fork."""
        from archskillkit.application.commands.governance import GovernanceApplicationService
        from archskillkit.application.models.governance import ProposalCreateCommand

        service = GovernanceApplicationService(self.world)
        return service.create_proposal(command)

    def diff_proposal(self, command):
        """Structural diff between base and candidate."""
        from archskillkit.application.commands.governance import GovernanceApplicationService
        from archskillkit.application.models.governance import ProposalDiffCommand

        service = GovernanceApplicationService(self.world)
        return service.diff_proposal(command)

    def review_proposal(self, command):
        """Fitness gate + structural diff against candidate."""
        from archskillkit.application.commands.governance import GovernanceApplicationService
        from archskillkit.application.models.governance import ProposalReviewCommand

        service = GovernanceApplicationService(self.world)
        return service.review_proposal(command)

    def promote_proposal(self, command):
        """Promote candidate to base."""
        from archskillkit.application.commands.governance import GovernanceApplicationService
        from archskillkit.application.models.governance import ProposalPromoteCommand

        service = GovernanceApplicationService(self.world)
        return service.promote_proposal(command)

    def reject_proposal(self, command):
        """Mark candidate as rejected."""
        from archskillkit.application.commands.governance import GovernanceApplicationService
        from archskillkit.application.models.governance import ProposalRejectCommand

        service = GovernanceApplicationService(self.world)
        return service.reject_proposal(command)

    # -- read queries -------------------------------------------------------

    def status(self):
        """Project status: identity, snapshot, typed next actions."""
        from archskillkit.application.queries.get_status import get_status

        return get_status(self.world, code_index=self.index)

    def explain(self, subject: str):
        """Explain an element or relation."""
        from archskillkit.application.queries.explain import explain

        return explain(self.world, subject)

    def search_code(self, query: str):
        """Search the code index."""
        from archskillkit.application.queries.analyze_impact import analyze_impact

        if self.index is None:
            return []
        hits = self.index.search(query) if self.index else []
        return hits

    def get_context(self, goal: str, subject: str | None = None, max_tokens: int = 1024, delta=None):
        """Compile a context pack for an agent goal.

        When ``delta`` (ArchitectureDelta) is provided, elements added or
        changed in the delta are ranked higher; removed elements are ranked
        lower (M6 delta-aware context).
        """
        from archskillkit.application.queries.context_query import ContextQuery
        from archskillkit.context import Budget, ContextCompiler

        compiler = ContextCompiler(self.world, self.index)
        pack = compiler.compile(
            goal, subject=subject,
            budget=Budget(max_tokens=max_tokens),
            delta=delta,
        )
        return pack

    def get_history(self, limit: int = 50, status: str | None = None):
        """Project run history."""
        from archskillkit.application.queries.history import get_history
        from archskillkit.runtime_state.run_ledger import RunLedger

        ledger = RunLedger()
        return get_history(ledger, limit=limit, status=status)

    def evidence(self):
        """Evidence items for the project."""
        from archskillkit.application.queries.evidence_query import get_evidence

        return get_evidence(self.world)

    def coverage(self):
        """Evidence coverage summary."""
        from archskillkit.application.queries.coverage_query import get_coverage

        return get_coverage(self.world)

    def gaps(self, status: str | None = None):
        """Knowledge gaps."""
        from archskillkit.application.queries.gaps_query import get_gaps

        return get_gaps(self.world, status=status)

    def findings(self):
        """Architecture findings."""
        from archskillkit.application.queries.findings_query import get_findings

        return get_findings(self.world)

    def ask(self, question: str):
        """Answer a natural-language architecture question (routes to impact or context)."""
        from archskillkit.application.queries.ask import ask

        return ask(self.world, self.index, question)

    def gate(
        self,
        min_coverage: float = 0.8,
        max_unknowns: int = 0,
        max_findings: int = 0,
        max_run_age_days: int = 30,
    ):
        """Evaluate the architecture fitness gate (V2.4 M3)."""
        from archskillkit.application.models.snapshot import ArchitectureSnapshot
        from archskillkit.application.queries.fitness import (
            FitnessThresholds,
            evaluate_gate,
        )
        from archskillkit.application.snapshot_builder import build_snapshot
        from archskillkit.runtime_state.run_ledger import RunLedger
        from archskillkit.runtime_state.waivers import WaiverLedger

        snapshot: ArchitectureSnapshot = build_snapshot(
            self.world, code_index=self.index
        )
        thresholds = FitnessThresholds(
            min_evidence_coverage=min_coverage,
            max_unknowns=max_unknowns,
            max_findings=max_findings,
            max_run_age_days=max_run_age_days,
        )
        result = evaluate_gate(
            self.world,
            snapshot,
            thresholds=thresholds,
            ledger=RunLedger(),
            waivers=WaiverLedger(),
        )
        return result, snapshot
