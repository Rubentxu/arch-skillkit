"""`archskillkit mine-conformance` — mine repeated architectural patterns.

Reads the Architecture World and surfaces relation-kind triples that appear
with sufficient support as ``ArchitectureRuleCandidate`` objects.

Schema: ``arch-skillkit/conformance-mining-v1``
"""

from __future__ import annotations

import argparse
import json
import sys

from archskillkit.conformance_miner import mine
from archskillkit.world import ArchitectureWorld

NAME = "mine-conformance"
NEEDS_WORLD = True

OUTPUT_SCHEMA = "arch-skillkit/conformance-mining-v1"


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

    with world:
        candidates = mine(world, min_support=args.min_support)

    envelope = {
        "schema": OUTPUT_SCHEMA,
        "project_id": world.project_id,
        "min_support": args.min_support,
        "candidates": [c.model_dump() for c in candidates],
    }
    print(json.dumps(envelope, indent=2))
    return 0
