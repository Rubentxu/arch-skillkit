"""`archskillkit explain <subject>` — evidence lineage as JSON.

Delivery adapter over the Explain use case (docs/v2/55 §2); errors use
the stable code SUBJECT_NOT_FOUND (§10).
"""

from __future__ import annotations

import argparse
import json
import sys

from archskillkit.application.queries.explain import SubjectNotFound, explain
from archskillkit.world import ArchitectureWorld

NAME = "explain"


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        NAME, help="evidence lineage for an element, claim, observation"
        " or evidence id (JSON)")
    p.add_argument("--repo", required=True)
    p.add_argument("subject")


def handle(args: argparse.Namespace, world: ArchitectureWorld) -> int:
    if not world.db_path.exists():
        print(f"error: no Architecture World for {world.project_id} "
              f"(run: archskillkit init --repo {world.root or '.'})",
              file=sys.stderr)
        return 1
    with world:
        try:
            explanation = explain(world, args.subject)
        except SubjectNotFound as exc:
            print(json.dumps({"code": exc.code, "message": str(exc)}))
            print(f"error: {exc}", file=sys.stderr)
            return 1
    print(json.dumps(explanation.model_dump(), indent=2))
    return 0
