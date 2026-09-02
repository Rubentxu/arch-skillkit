"""Typed ContextQuery and CompileContext use case (V2.4 M2, docs/v2/56,
67 slice 6).

The query is the single input contract for context compilation: CLI,
MCP and the future Control Plane express the same typed intent, and
natural language (`ask`) must resolve to exactly this shape — NL and
typed inputs are equivalent when they produce the same query.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from archskillkit.context import Budget, ContextCompiler, ContextPack

CONTEXT_QUERY_SCHEMA = "arch-skillkit/context-query-v1"


class ContextQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema: Literal["arch-skillkit/context-query-v1"] = (
        CONTEXT_QUERY_SCHEMA)  # type: ignore[assignment]
    goal: str = Field(min_length=1)
    subject: str | None = None
    budget: Budget = Field(default_factory=Budget)


def compile_context(compiler: ContextCompiler,
                    query: ContextQuery) -> ContextPack:
    """Run a typed query through the compiler. Read-only: compiling
    never mutates the world."""
    return compiler.compile(goal=query.goal, subject=query.subject,
                            budget=query.budget)
