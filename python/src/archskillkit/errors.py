"""Domain exceptions shared across ports, repositories and use cases."""

from __future__ import annotations


class PromotionError(Exception):
    """A promotion/proposal invariant was violated."""
