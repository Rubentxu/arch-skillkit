"""`archskillkit delta` — compare two pre-built snapshot state files
(V2.4 M3, docs/v2/58, slice 11).

Takes two arch-skillkit/snapshot-state-v1 JSON files and emits the
ArchitectureDelta as JSON or PR-comment-friendly Markdown. Read-only;
deterministic; the same two files always yield the same output.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from archskillkit.application.queries.delta import (
    SnapshotState,
    compute_delta_states,
)
from archskillkit.application.queries.delta_report import (
    render_delta_markdown,
)

NAME = "delta"
NEEDS_WORLD = False


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        NAME, help="compare two pre-built snapshot state JSON files")
    p.add_argument("--base-state", required=True,
                   help="path to the base snapshot state JSON")
    p.add_argument("--head-state", required=True,
                   help="path to the head snapshot state JSON")
    p.add_argument("--project", default="",
                   help="project label for the markdown header")
    p.add_argument("--format", choices=["json", "markdown"],
                   default="json")
    p.add_argument("--out", help="write the report to PATH instead of"
                   " stdout")


def _load(path: str) -> SnapshotState:
    text = Path(path).read_text()
    return SnapshotState.from_json(text)


def handle(args: argparse.Namespace, world=None) -> int:
    try:
        base = _load(args.base_state)
        head = _load(args.head_state)
    except (json.JSONDecodeError, KeyError, FileNotFoundError) as exc:
        print(f"error: invalid state file: {exc}", file=sys.stderr)
        return 2
    delta = compute_delta_states(
        base, head,
        base_snapshot_id=f"state:{Path(args.base_state).name}",
        head_snapshot_id=f"state:{Path(args.head_state).name}",
    )
    if args.format == "markdown":
        out = render_delta_markdown(delta, project=args.project)
    else:
        out = json.dumps(delta.model_dump(), indent=2) + "\n"
    if args.out:
        Path(args.out).write_text(out)
    else:
        sys.stdout.write(out)
    return 0
