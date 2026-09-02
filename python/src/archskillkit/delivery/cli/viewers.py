"""`archskillkit viewers` — viewer registry as JSON (docs/v2/54 §6).

Host-level command: no repository involved, same registry `ark doctor`
will consume for its capability manifest.
"""

from __future__ import annotations

import argparse
import json

from archskillkit.viewers.registry import ViewerRegistry

NAME = "viewers"
NEEDS_WORLD = False


def register(subparsers: argparse._SubParsersAction) -> None:
    subparsers.add_parser(
        NAME, help="known viewers, formats and live availability (JSON)")


def handle(args: argparse.Namespace) -> int:
    print(json.dumps({"schema": "arch-skillkit/viewers-v1",
                      "viewers": ViewerRegistry().status()}, indent=2))
    return 0
