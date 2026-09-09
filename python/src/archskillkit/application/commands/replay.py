"""Replay fixture application service (V2.5 M2, ADR-0049).

Canonical application-layer implementation of the fixture replay workflow.
"""

from __future__ import annotations

from archskillkit.application.models.replay import (
    ReplayFixtureCommand,
    ReplayResult,
)


class ReplayApplicationService:
    """Application-layer implementation of the fixture replay workflow.

    Replays a captured scanner-payload fixture end to end and compares the
    resulting snapshot against the golden.
    """

    def replay_fixture(
        self,
        cmd: ReplayFixtureCommand,
        *,
        env: dict[str, str] | None = None,
    ) -> ReplayResult:
        """Replay the captured pipeline against ``fixture_dir``.

        Parameters
        ----------
        cmd
            ReplayFixtureCommand with fixture_dir and write_golden.
        env
            Optional environment overrides for the replay.

        Returns
        -------
        ReplayResult
            Replay verdict with match/drift information.
        """
        # Import here to avoid circular dependency at module load time
        from archskillkit.delivery.cli.replay_fixture import run as replay_run

        result = replay_run(
            cmd.fixture_dir,
            write_golden=cmd.write_golden,
            env=env,
        )
        return result
