"""Code Intelligence Provider SPI (V2.5 M5, ADR-0049).

This package defines the ``CodeGraphQueryPort`` Protocol that application
layer code must depend on, and the SQLite-backed adapter that satisfies
it (``CodeGraphSqliteAdapter``). The legacy ``archskillkit.codeindex``
module remains as the concrete implementation; this package is the
boundary that lets the application stay decoupled from any particular
indexing technology.

Migration recipe (already applied in v0.13.0):

1. ``ArchSkillKitApplication`` owns the canonical ``CodeIndex`` instance
   and exposes it as ``app.index`` (lazy).
2. Delivery adapters (``cli.py``, ``delivery/cli/*.py``) consume
   ``getattr(world, "_arch_app", None).index`` instead of constructing
   ``CodeIndex(...)`` directly.
3. Application layer (``promotion.py``, ``context.py``) consumes
   ``CodeGraphQueryPort`` — the Protocol — not the concrete class.

ADR-0049 verification: ``rg "CodeGraphQueryPort" python/src/`` returns
non-zero matches (the Protocol definition here).
"""

from archskillkit.codegraph.port import CodeGraphQueryPort
from archskillkit.codegraph.sqlite_adapter import (
    CodeGraphSqliteAdapter,
    satisfies_port,
)

__all__ = ["CodeGraphQueryPort", "CodeGraphSqliteAdapter", "satisfies_port"]
