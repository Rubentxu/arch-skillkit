"""Minimal agent-facing facade: `python -m archskillkit <command> --repo PATH`.

Read-only towards the analyzed repository: the only git invocations are
rev-parse / config --get / remote. Exit codes: 0 ok, 1 world/usage error
at runtime, 2 argument or precondition failure.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from archskillkit.ids import RepoNotFound
from archskillkit.packs.arch_core import ObservationData
from archskillkit.world import ArchitectureWorld


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="archskillkit",
        description="ArchSkillKit V2 Architecture World facade.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    for name in ("init", "state", "replay-verify"):
        p = sub.add_parser(name)
        p.add_argument("--repo", required=True)

    p_obs = sub.add_parser("record-observation")
    p_obs.add_argument("--repo", required=True)
    p_obs.add_argument("--payload", required=True,
                       help="JSON file following design/schemas/observation.yaml")

    args = parser.parse_args(argv)

    try:
        world = ArchitectureWorld.for_repo(args.repo)
    except RepoNotFound as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.command == "init":
        return _cmd_init(world)
    if args.command == "state":
        return _cmd_state(world)
    if args.command == "replay-verify":
        return _cmd_replay_verify(world)
    if args.command == "record-observation":
        return _cmd_record_observation(world, Path(args.payload))
    parser.error(f"unknown command: {args.command}")
    return 2


def _cmd_init(world: ArchitectureWorld) -> int:
    world.open()
    try:
        world.ensure_project()
    finally:
        world.close()
    print(json.dumps({
        "project_id": world.project_id,
        "name": world.project_name,
        "workspace": str(world.workspace),
        "activegraph_db": str(world.db_path),
    }))
    return 0


def _require_world(world: ArchitectureWorld) -> str | None:
    if not world.db_path.exists():
        print(
            f"error: no Architecture World for {world.project_id} "
            f"(run: archskillkit init --repo {world.root or '.'})",
            file=sys.stderr,
        )
        return None
    return str(world.db_path)


def _cmd_state(world: ArchitectureWorld) -> int:
    if _require_world(world) is None:
        return 1
    with world:
        print(json.dumps(world.snapshot(), indent=2))
    return 0


def _cmd_replay_verify(world: ArchitectureWorld) -> int:
    if _require_world(world) is None:
        return 1
    with world:
        report = world.replay_verify()
    if report.ok:
        print(f"replay OK: {report.objects} objects, {report.relations} relations, "
              f"{report.events} events ({report.detail})")
        return 0
    print(f"replay FAILED: {report.detail}", file=sys.stderr)
    return 1


def _cmd_record_observation(world: ArchitectureWorld, payload: Path) -> int:
    try:
        observation = ObservationData.model_validate_json(payload.read_text())
    except (ValidationError, OSError) as exc:
        print(f"error: invalid observation payload: {exc}", file=sys.stderr)
        return 2
    with world:
        obs_id = world.record_observation(observation)
    print(obs_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
