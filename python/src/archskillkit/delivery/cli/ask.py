"""`archskillkit ask <question>` — NL entry point over the typed
queries (docs/v2/55 §3). Deterministic parsing, same JSON contract as
the underlying use cases; the intent is echoed so callers can see how
their question was routed.
"""

from __future__ import annotations

import argparse
import json
import sys

from archskillkit.application.queries.ask import ask
from archskillkit.world import ArchitectureWorld

NAME = "ask"
NEEDS_WORLD = True


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        NAME, help="ask a natural-language architecture question"
        " (routes to context or impact; JSON)")
    p.add_argument("--repo", required=True)
    p.add_argument("question")


def handle(args: argparse.Namespace, world: ArchitectureWorld) -> int:
    if not world.db_path.exists():
        print(f"error: no Architecture World for {world.project_id} "
              f"(run: archskillkit init --repo {world.root or '.'})",
              file=sys.stderr)
        return 1
    # Access app's index so lifecycle stays in Composition Root (M3 slice 3).
    app = getattr(world, "_arch_app", None)
    if app is None or app.index is None:
        print(f"error: no code.sqlite for {world.project_id} "
              f"(run: archskillkit ingest-code --repo {world.root or '.'})",
              file=sys.stderr)
        return 1
    with world:
        intent, result = ask(world, app.index, args.question)
    print(json.dumps({
        "schema": "arch-skillkit/ask-result-v1",
        "intent": intent.model_dump(),
        "result": result.model_dump(),
    }, indent=2))
    return 0
