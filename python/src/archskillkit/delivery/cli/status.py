"""`archskillkit status` — revisions + typed next actions as JSON.

Delivery adapter: argument parsing, one application use case, output.
No architecture logic here (ADR-0045); contract docs/v2.55 §2/§4/§5.
"""

from __future__ import annotations

import argparse
import json
import sys

from archskillkit.application.queries.get_status import get_status
from archskillkit.world import ArchitectureWorld

NAME = "status"
NEEDS_WORLD = True


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        NAME, help="project status: revisions snapshot + typed next"
        " actions (JSON)")
    p.add_argument("--repo", required=True)


def handle(args: argparse.Namespace, world: ArchitectureWorld) -> int:
    if not world.db_path.exists():
        print(f"error: no Architecture World for {world.project_id} "
              f"(run: archskillkit init --repo {world.root or '.'})",
              file=sys.stderr)
        return 1
    # Route through Composition Root when app is available.
    # Fall back to get_status for direct CLI invocation without app.
    app = getattr(world, "_arch_app", None)
    if app is not None:
        result = app.status()
    else:
        result = get_status(world, code_index=None)
    print(json.dumps(result.model_dump(), indent=2))
    return 0
