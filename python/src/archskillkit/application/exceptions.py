"""Application-level exceptions (V2.5 M5).

Re-exports exceptions that live in infrastructure packages so the
application layer does not need to import them directly (ARC-005).
"""

from __future__ import annotations


class AmbiguousSymbolError(Exception):
    """Raised when symbol resolution finds multiple candidates."""

    def __init__(self, message: str, candidates: list[dict] | None = None):
        super().__init__(message)
        self.candidates = candidates or []
