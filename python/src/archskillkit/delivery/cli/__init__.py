"""CLI delivery adapters (V2.4, docs/v2/67 slices 4-5).

Each module owns its subcommand end to end: `register` declares the
arguments, `handle` invokes the application layer and prints JSON.
World-dependent commands declare NEEDS_WORLD and receive the world;
host-level commands (viewers, mcp) don't. `cli.py` stays parser/composition
root; legacy commands keep their existing handlers. `ark schema`
arrives with M1.
"""

from archskillkit.delivery.cli import (
    ask,
    control_plane,
    delta,
    distill_sensors,
    explain,
    gate,
    mcp,
    proposals,
    replay_candidate,
    replay_fixture,
    schema,
    simulate,
    status,
    view,
    viewers,
)

COMMANDS = (
    status,
    explain,
    viewers,
    schema,
    view,
    ask,
    delta,
    gate,
    proposals,
    simulate,
    replay_fixture,
    replay_candidate,
    mcp,
    control_plane,
    distill_sensors,
)

__all__ = [
    "COMMANDS",
    "ask",
    "control_plane",
    "delta",
    "distill_sensors",
    "explain",
    "gate",
    "mcp",
    "proposals",
    "replay_candidate",
    "replay_fixture",
    "schema",
    "simulate",
    "status",
    "view",
    "viewers",
]
