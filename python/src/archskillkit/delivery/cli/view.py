"""`archskillkit view` — open a projection artifact in a viewer
(docs/v2/54 §4/§6, docs/v2/55 §2 `LaunchViewer`).

The artifact must already exist (projection generation is a separate,
viewer-independent command). Managed servers keep running after this
command exits; their PID is registered for stop/orphan cleanup.
"""

from __future__ import annotations

import argparse
import json
import sys

from archskillkit.projections.writer import ARTIFACT_PATHS
from archskillkit.runtime_state.runtime_registry import RuntimeRegistry
from archskillkit.viewers.contract import ViewerUnavailable
from archskillkit.viewers.registry import ViewerRegistry, launch
from archskillkit.world import ArchitectureWorld

NAME = "view"
NEEDS_WORLD = True


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        NAME, help="open a projection artifact in the best available"
        " viewer (JSON session summary)")
    p.add_argument("--repo", required=True)
    p.add_argument("--format", required=True,
                   choices=sorted(ARTIFACT_PATHS))
    p.add_argument("--with", dest="with_viewer", default=None,
                   help="explicit viewer id (default: route by format)")


def handle(args: argparse.Namespace, world: ArchitectureWorld) -> int:
    if not world.db_path.exists():
        print(f"error: no Architecture World for {world.project_id} "
              f"(run: archskillkit init --repo {world.root or '.'})",
              file=sys.stderr)
        return 1
    artifact = world.workspace / ARTIFACT_PATHS[args.format]
    if not artifact.exists():
        print(f"error: no {args.format} artifact at {artifact} "
              f"(run: archskillkit project --repo {world.root or '.'} "
              f"--format {args.format})", file=sys.stderr)
        return 1
    registry = ViewerRegistry()
    try:
        adapter = registry.route(args.format, explicit=args.with_viewer)
    except ViewerUnavailable as exc:
        print(json.dumps({"code": exc.code, "message": str(exc)}))
        print(f"error: {exc}", file=sys.stderr)
        return 1
    session = launch(adapter, artifact,
                     runtime_registry=RuntimeRegistry())
    print(json.dumps({
        "schema": "arch-skillkit/view-session-v1",
        "viewer": session.viewer_id,
        "pid": session.pid,
        "managed": session.managed,
        "artifact": str(artifact),
        "argv": session.argv,
    }, indent=2))
    return 0
