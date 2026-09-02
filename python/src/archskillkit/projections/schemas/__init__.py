"""External format schemas for the projection validation scripts.

These are minimal, opinionated, and kept under our own control so the
validation scripts do not need to fetch a network resource at run time.
The JSON Canvas 1.0 schema here follows the public spec at
https://jsoncanvas.org/schema/1.0 — only the parts our adapters emit
(and the parts Obsidian Canvas reads) are constrained. Compatibility
with other JSON Canvas consumers is preserved because we reject only
what would be ambiguous to a downstream reader.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_SCHEMAS_DIR = Path(__file__).parent


@lru_cache(maxsize=8)
def load_schema(name: str) -> dict:
    """Load a schema by short name (e.g. 'jsoncanvas-1.0')."""
    path = _SCHEMAS_DIR / f"{name}.schema.json"
    return json.loads(path.read_text())