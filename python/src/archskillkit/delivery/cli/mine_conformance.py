"""`archskillkit mine-conformance` — mine repeated architectural patterns.

Reads the Architecture World and surfaces relation-kind triples that appear
with sufficient support as ``ArchitectureRuleCandidate`` objects.

Delivery adapter (V2.5 M3): routes through ``app.mine_conformance()``
(ADR-0057, M2 composition root). Falls back to direct ``mine()`` for
direct CLI invocation without the bootstrap app.

Schema: ``arch-skillkit/conformance-mining-v1``
"""

from __future__ import annotations

import argparse
import json
import sys

from archskillkit.application.models.conformance import (
    MineConformanceCommand,
    MineConformanceResult,
)
from archskillkit.world import ArchitectureWorld

NAME = "mine-conformance"
NEEDS_WORLD = True

OUTPUT_SCHEMA = "arch-skillkit/conformance-mining-v1"


def _direct_mine(world, cmd: MineConformanceCommand):
    """Fallback path: invoke mine() directly when composition root is absent."""
    from archskillkit.conformance_miner import mine

    with world:
        candidates = mine(world, min_support=cmd.min_support)
    return MineConformanceResult(
        schema=OUTPUT_SCHEMA,
        project_id=world.project_id,
        min_support=cmd.min_support,
        candidates=[c.model_dump() for c in candidates],
    )


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        NAME,
        help="mine repeated architectural patterns and propose conformance rule candidates",
    )
    p.add_argument("--repo", required=True, help="Path to the repository")
    p.add_argument(
        "--min-support",
        type=int,
        default=3,
        help="Minimum occurrence count for a pattern to become a candidate (default: 3)",
    )


def handle(args: argparse.Namespace, world: ArchitectureWorld) -> int:
    if not world.db_path.exists():
        print(
            f"error: no Architecture World for {world.project_id} "
            f"(run: archskillkit init --repo {world.root or '.'})",
            file=sys.stderr,
        )
        return 1

    app = getattr(world, "_arch_app", None)
    cmd = MineConformanceCommand(min_support=args.min_support)

    with world:
        if app is not None:
            result = app.mine_conformance(cmd)
        else:
            result = _direct_mine(world, cmd)

    print(json.dumps(result.model_dump(mode="json"), indent=2))
    return 0
