"""CLI delivery adapters (V2.4, docs/v2/67 slices 4-5).

Each module owns its subcommand end to end: `register` declares the
arguments, `handle` invokes the application layer and prints JSON.
World-dependent commands declare NEEDS_WORLD and receive the world;
host-level commands (viewers) don't. `cli.py` stays parser/composition
root; legacy commands keep their existing handlers. `ark schema`
arrives with M1.
"""

from archskillkit.delivery.cli import explain, status, viewers

COMMANDS = (status, explain, viewers)

__all__ = ["COMMANDS", "explain", "status", "viewers"]
