"""`archskillkit schema [name]` — self-describing output contracts
(docs/v2/55 §4: "`ark schema` expone schemas de outputs y objetos
relevantes").

Schemas are generated from the pydantic models, so they can never
drift from the code that emits the outputs. M1 acceptance: `schema
status` must validate a real `status` output.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable

from archskillkit.application.models.actions import ActionSuggestion
from archskillkit.application.models.snapshot import ArchitectureSnapshot
from archskillkit.application.queries.explain import Explanation
from archskillkit.application.queries.get_status import StatusResult
from archskillkit.runtime_state.run_ledger import RunRecord
from archskillkit.viewers.contract import ViewerDescriptor

NAME = "schema"
NEEDS_WORLD = False

SCHEMA_TARGETS: dict[str, Callable[[], dict]] = {
    "status": StatusResult.model_json_schema,
    "explain": Explanation.model_json_schema,
    "snapshot": ArchitectureSnapshot.model_json_schema,
    "run-record": RunRecord.model_json_schema,
    "action-suggestion": ActionSuggestion.model_json_schema,
    "viewer-descriptor": ViewerDescriptor.model_json_schema,
}


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        NAME, help="JSON schema of a command output or domain object")
    p.add_argument("name", nargs="?", default=None,
                   help=f"one of: {', '.join(sorted(SCHEMA_TARGETS))}")


def handle(args: argparse.Namespace) -> int:
    envelope = {"schema": "arch-skillkit/schema-output-v1"}
    if not args.name:
        print(json.dumps({**envelope, "available": sorted(SCHEMA_TARGETS)},
                         indent=2))
        return 0
    target = SCHEMA_TARGETS.get(args.name)
    if target is None:
        print(f"error: unknown schema {args.name!r} (available:"
              f" {', '.join(sorted(SCHEMA_TARGETS))})", file=sys.stderr)
        return 2
    print(json.dumps({**envelope, "name": args.name,
                      "json_schema": target()}, indent=2))
    return 0
