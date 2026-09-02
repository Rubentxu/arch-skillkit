"""MCP server adapter for archskillkit (V2.4 M4, docs/v2/55 §3).

Exposes read-only architecture knowledge to MCP-capable clients
(LLM agents, control plane, IDE integrations). The tools here are
deliberately read-only — proposing mutations goes through the
candidate -> review -> promote path on the CLI side, never through
MCP write tools (slice 14).

Every tool emits a schema-bound JSON envelope. Tool names are
namespaced with `arch_` so an LLM agent can pick them without
colliding with other servers in the same context.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from archskillkit.application.queries.explain import SubjectNotFound, explain
from archskillkit.application.queries.get_status import get_status
from archskillkit.application.queries.history import get_history
from archskillkit.codeindex import CodeIndex
from archskillkit.context import Budget, ContextCompiler
from archskillkit.runtime_state.run_ledger import RunLedger
from archskillkit.world import ArchitectureWorld

NAME = "mcp"
NEEDS_WORLD = False


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        NAME, help="run the MCP server over stdio (read-only)")
    p.add_argument("--repo", required=True)


def _tool(name: str, description: str,
          schema: dict[str, Any]) -> Tool:
    return Tool(name=name, description=description,
                inputSchema=schema)


def _envelope(payload: dict | list | str) -> list[TextContent]:
    text = payload if isinstance(payload, str) else json.dumps(
        payload, indent=2)
    return [TextContent(type="text", text=text)]


def build_server(repo_path: str) -> Server:
    server = Server("archskillkit")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            _tool("arch_get_status",
                  "Return the project status envelope: snapshot, "
                  "knowledge coverage, ledger.",
                  {"type": "object", "properties": {},
                   "additionalProperties": False}),
            _tool("arch_get_explain",
                  "Return evidence lineage for a subject (element, "
                  "claim, observation or evidence id).",
                  {"type": "object",
                   "properties": {"subject": {"type": "string"}},
                   "required": ["subject"], "additionalProperties": False}),
            _tool("arch_search_code",
                  "Search the code index by symbol or path prefix.",
                  {"type": "object",
                   "properties": {"query": {"type": "string"}},
                   "required": ["query"], "additionalProperties": False}),
            _tool("arch_get_context",
                  "Compile a budgeted context pack from a goal string.",
                  {"type": "object",
                   "properties": {
                       "goal": {"type": "string"},
                       "subject": {"type": "string"},
                       "max_tokens": {"type": "integer",
                                       "minimum": 1, "maximum": 8192},
                   },
                   "required": ["goal"], "additionalProperties": False}),
            _tool("arch_get_history",
                  "List run history summaries from the RunLedger.",
                  {"type": "object",
                   "properties": {
                       "limit": {"type": "integer", "minimum": 1,
                                 "default": 50},
                       "status": {"type": "string"},
                   },
                   "additionalProperties": False}),
        ]

    def _world() -> tuple[ArchitectureWorld, CodeIndex | None]:
        world = ArchitectureWorld.for_repo(repo_path).open()
        index_path = world.workspace / "code.sqlite"
        index = CodeIndex(index_path).open() if index_path.exists() \
            else None
        return world, index

    @server.call_tool()
    async def call_tool(name: str,
                        arguments: dict[str, Any]) -> list[TextContent]:
        world, index = _world()
        try:
            if name == "arch_get_status":
                return _envelope(get_status(world, code_index=index
                                            ).model_dump())
            if name == "arch_get_explain":
                try:
                    explanation = explain(world,
                                           arguments.get("subject", ""))
                except SubjectNotFound as exc:
                    return _envelope(
                        {"code": exc.code, "message": str(exc),
                         "subject": arguments.get("subject", "")})
                return _envelope(explanation.model_dump())
            if name == "arch_search_code":
                query = arguments.get("query", "")
                hits = index.search(query) if index is not None else []
                return _envelope({"query": query, "hits": hits})
            if name == "arch_get_context":
                goal = arguments.get("goal", "")
                subject = arguments.get("subject")
                max_tokens = int(arguments.get("max_tokens", 1024))
                compiler = ContextCompiler(world, index)
                pack = compiler.compile(goal, subject=subject,
                                        budget=Budget(max_tokens=max_tokens))
                return _envelope(pack.model_dump())
            if name == "arch_get_history":
                limit = int(arguments.get("limit", 50))
                status = arguments.get("status")
                ledger = RunLedger()
                history = get_history(ledger, limit=limit, status=status)
                return _envelope(history.model_dump())
            return _envelope({"error": f"unknown tool {name!r}"})
        finally:
            if index is not None:
                index.close()
            world.close()

    return server


def handle(args: argparse.Namespace, world=None) -> int:
    repo_path = str(Path(args.repo).resolve())
    server = build_server(repo_path)

    async def run() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream,
                             server.create_initialization_options())

    try:
        asyncio.run(run())
    except (KeyboardInterrupt, asyncio.CancelledError):
        return 0
    return 0
