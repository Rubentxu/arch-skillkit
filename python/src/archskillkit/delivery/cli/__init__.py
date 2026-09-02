"""CLI delivery adapters (V2.4, docs/v2/67 slice 4).

Each module owns its subcommand end to end: `register` declares the
arguments, `handle` invokes the application layer and prints JSON.
`cli.py` stays parser/composition root; legacy commands keep their
existing handlers (no argparse rewrite). `ark schema` arrives with M1.
"""

from archskillkit.delivery.cli import explain, status

COMMANDS = (status, explain)

__all__ = ["COMMANDS", "explain", "status"]
