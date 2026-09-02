"""MCP server adapter for archskillkit (V2.4 M4, docs/v2/55 §3).

Exposes read-only architecture knowledge to MCP-capable clients
(LLM agents, control plane, IDE integrations). The base tools here
are read-only.

Admin tools implement the candidate -> review -> promote workflow
and are gated behind ARCH_SKILLKIT_ADMIN=1 / --admin (V2.4 M4,
docs/v2/59 M4 acceptance: "admin disabled by default"). When the
gate is off, admin tools are not listed AND any call to them
returns the stable ADMIN_DISABLED code via McpError so the wire
layer marks isError=True.

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
from mcp.shared.exceptions import McpError
from mcp.types import ErrorData, TextContent, Tool

from archskillkit.agent_governance import (
    load_skill_revisions,
    prompt_specs_registry,
)
from archskillkit.application.queries.explain import SubjectNotFound, explain
from archskillkit.application.queries.get_status import get_status
from archskillkit.application.queries.history import get_history
from archskillkit.codeindex import CodeIndex
from archskillkit.context import Budget, ContextCompiler
from archskillkit.delivery.admin import (
    ADMIN_TOOLS,
    AdminDisabledError,
    admin_enabled,
)
from archskillkit.delivery.cli.proposals import (
    _candidate_status,
    handle_create,
    handle_diff,
    handle_promote,
    handle_reject,
    handle_review,
)
from archskillkit.runtime_state.run_ledger import RunLedger
from archskillkit.world import ArchitectureWorld

NAME = "mcp"
NEEDS_WORLD = False


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(NAME, help="run the MCP server over stdio (read-only)")
    p.add_argument("--repo", required=True)
    p.add_argument(
        "--admin",
        action="store_true",
        help="enable admin tools (candidate workflow:"
        " propose list/create/diff/review/promote/reject)."
        " Default: disabled. Equivalent to"
        " ARCH_SKILLKIT_ADMIN=1.",
    )


def _tool(name: str, description: str, schema: dict[str, Any]) -> Tool:
    return Tool(name=name, description=description, inputSchema=schema)


def _envelope(payload: dict | list | str) -> list[TextContent]:
    text = payload if isinstance(payload, str) else json.dumps(payload, indent=2)
    return [TextContent(type="text", text=text)]


# ---------- admin tool helpers (delegate to proposals.py) ----------


def _envelope_or_error(envelope: dict[str, Any]) -> dict[str, Any]:
    """Pass through the proposal envelope; raise McpError on `error`
    field so wire layer reports isError=True with a stable code."""
    if "error" in envelope:
        raise McpError(ErrorData(code=-32603, message=json.dumps(envelope), data=envelope))
    return envelope


class _ArgNamespace:
    """Minimal argparse.Namespace stand-in for the proposals handlers.

    The proposals handlers are wired through argparse on the CLI
    side; from MCP we drive them with a tiny namespace so the
    handlers stay single-source-of-truth and never duplicate
    validation logic."""

    def __init__(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


def _handle_admin_propose_list(
    arguments: dict[str, Any], world: ArchitectureWorld
) -> dict[str, Any]:
    """List candidate proposals (proposal-* runs)."""
    from archskillkit.agent_governance import get_proposal_metadata

    rows = []
    for run_id in world.list_runs():
        if not run_id.startswith("proposal-"):
            continue
        status = _candidate_status(world, run_id)
        row: dict[str, Any] = {"run_id": run_id, "status": status}
        metadata = get_proposal_metadata(world, run_id)
        if metadata is not None:
            row["metadata"] = metadata.to_object()
        rows.append(row)
    return {
        "schema": "arch-skillkit/proposals-list-v1",
        "project_id": world.project_id,
        "candidates": rows,
    }


def _handle_admin_prompt_registry(
    arguments: dict[str, Any], world: ArchitectureWorld
) -> dict[str, Any]:
    """List the PromptSpec(s) the embedded LLM can declare.

    Every entry carries name + version + sha-256 digest. The
    digest is the stable identifier a candidate MUST record to
    prove which spec produced it."""
    specs = []
    for spec in prompt_specs_registry().values():
        specs.append(
            {
                "name": spec.name,
                "version": spec.version,
                "digest": spec.digest(),
            }
        )
    return {
        "schema": "arch-skillkit/prompt-registry-v1",
        "specs": specs,
    }


def _handle_admin_skill_registry(
    arguments: dict[str, Any], world: ArchitectureWorld
) -> dict[str, Any]:
    """List the versioned skills the embedded LLM can declare.

    Only skills with a `version:` line in SKILL.md frontmatter
    appear; unversioned skills are excluded by design (they have
    no stable provenance)."""
    from archskillkit.delivery.cli.proposals import _default_skills_root

    root = _default_skills_root()
    revisions = load_skill_revisions(root)
    return {
        "schema": "arch-skillkit/skill-registry-v1",
        "skills_root": str(root),
        "skills": [r.model_dump() for r in revisions],
    }


def _handle_admin_simulate(arguments: dict[str, Any], world: ArchitectureWorld) -> dict[str, Any]:
    """Apply a counterfactual change to a throwaway fork.

    Delegates to ``delivery.cli.simulate.run`` so wire calls reuse
    the same logic (fork, apply verb, evaluate gate, drop fork,
    assert base digest unchanged). On SimulationError (unknown
    element, invalid category, base-mutated), raises McpError so
    the wire layer marks ``isError=True`` with a stable code in the
    envelope data.
    """
    from archskillkit.delivery.cli.simulate import SimulationError, run

    verb = arguments.get("verb", "")
    payload: dict[str, Any] = {"verb": verb}
    if verb == "relation_add":
        payload["source"] = arguments.get("source", "")
        payload["target"] = arguments.get("target", "")
        payload["kind"] = arguments.get("kind", "depends_on")
    elif verb == "move":
        payload["element"] = arguments.get("element", "")
        payload["to"] = arguments.get("to", "")
    elif verb == "delete":
        payload["element"] = arguments.get("element", "")
    else:
        envelope = {
            "schema": "arch-skillkit/simulation-result-v1",
            "error": "INVALID_VERB",
            "message": f"unknown verb {verb!r}; expected one of relation_add, move, delete",
        }
        raise McpError(ErrorData(code=-32603, message=json.dumps(envelope), data=envelope))
    try:
        result = run(world, verb, **{k: v for k, v in payload.items() if k != "verb"})
    except SimulationError as exc:
        envelope = exc.to_envelope()
        raise McpError(ErrorData(code=-32603, message=json.dumps(envelope), data=envelope))
    return result.model_dump()


def _call_proposals_handler(handler, world: ArchitectureWorld, **kwargs: Any) -> dict[str, Any]:
    """Drive a proposals handler with a synthetic namespace; the
    handler returns 0/1 and prints to stdout. We don't want stdout
    noise on the wire, so we capture the JSON envelope via a
    lightweight in-process call.

    The proposals handlers print the envelope to stdout, then
    return an exit code. We re-run them with stdout AND stderr
    redirected to a buffer and parse the envelope back. This keeps
    the handlers single-source-of-truth without rewriting them as
    return-value functions (a bigger refactor we don't need today).

    Precedence on failure: try stderr first (the error path), then
    stdout (the success path that nonetheless failed at a later
    step)."""
    import contextlib
    import io

    out_buf = io.StringIO()
    err_buf = io.StringIO()
    ns = _ArgNamespace(**kwargs)
    with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
        rc = handler(ns, world)
    out_text = out_buf.getvalue().strip()
    err_text = err_buf.getvalue().strip()
    if rc != 0:
        # Error path: handler writes envelope to stderr. Fall back
        # to stdout if a future handler writes to stdout on failure.
        text = err_text or out_text
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = {"error": "HANDLER_FAILED", "message": text or "handler returned non-zero"}
        return _envelope_or_error(payload)
    try:
        return json.loads(out_text)
    except json.JSONDecodeError:
        return {"error": "BAD_ENVELOPE", "message": out_text}


# ---------- server ----------


def build_server(repo_path: str, *, admin: bool | None = None) -> Server:
    """Build an MCP server instance.

    admin: None -> resolve via env / CLI flag at call time.
           True/False -> force the gate."""
    if admin is None:
        admin = admin_enabled()

    server = Server("archskillkit")

    # Tool descriptors for admin tools. Centralised so the listing
    # gate and the call gate stay in sync.
    admin_tool_descriptors = {
        "arch_propose_list": _tool(
            "arch_propose_list",
            "List candidate proposals (proposal-* runs) with "
            "their current status (open|approved|rejected). "
            "Admin tool — requires --admin.",
            {"type": "object", "properties": {}, "additionalProperties": False},
        ),
        "arch_propose_create": _tool(
            "arch_propose_create",
            "Fork the base world into a candidate run. The "
            "candidate is a sibling run prefixed with proposal-; "
            "the base world is never mutated. Optional "
            "prompt_spec + skill[] record provenance metadata "
            "into the fork. Admin tool.",
            {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "minLength": 1},
                    "prompt_spec": {
                        "type": "string",
                        "description": "PromptSpec name (e.g. architecture-analyst)",
                    },
                    "skill": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Skill names the agent was "
                        "operating under (content-addressed)",
                    },
                },
                "required": ["name"],
                "additionalProperties": False,
            },
        ),
        "arch_propose_diff": _tool(
            "arch_propose_diff",
            "Structural diff between the base world and a candidate. Admin tool.",
            {
                "type": "object",
                "properties": {"name": {"type": "string", "minLength": 1}},
                "required": ["name"],
                "additionalProperties": False,
            },
        ),
        "arch_propose_review": _tool(
            "arch_propose_review",
            "Evaluate the fitness gate against a candidate's "
            "snapshot, plus the structural diff. Returns the gate "
            "verdict (pass/warn/fail), the diff, and per-dimension "
            "fitness. Admin tool.",
            {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "minLength": 1},
                    "min_coverage": {
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 1.0,
                        "default": 0.8,
                    },
                    "max_unknowns": {"type": "integer", "minimum": 0, "default": 0},
                    "max_findings": {"type": "integer", "minimum": 0, "default": 0},
                    "max_run_age_days": {"type": "integer", "minimum": 0, "default": 30},
                },
                "required": ["name"],
                "additionalProperties": False,
            },
        ),
        "arch_propose_promote": _tool(
            "arch_propose_promote",
            "Promote a candidate to base. Records approval, then "
            "merges. Idempotent only by record; a second call on "
            "an already-approved candidate returns PROMOTION_FAILED. "
            "Admin tool.",
            {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "minLength": 1},
                    "approved_by": {"type": "string", "minLength": 1},
                },
                "required": ["name", "approved_by"],
                "additionalProperties": False,
            },
        ),
        "arch_propose_reject": _tool(
            "arch_propose_reject",
            "Mark a candidate as rejected. Does NOT mutate base. Admin tool.",
            {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "minLength": 1},
                    "actor": {"type": "string", "minLength": 1},
                },
                "required": ["name", "actor"],
                "additionalProperties": False,
            },
        ),
        "arch_prompt_registry": _tool(
            "arch_prompt_registry",
            "List the PromptSpec(s) the embedded LLM can declare. "
            "Every entry carries name + version + sha-256 digest. "
            "Admin tool.",
            {"type": "object", "properties": {}, "additionalProperties": False},
        ),
        "arch_skill_registry": _tool(
            "arch_skill_registry",
            "List the versioned skills the embedded LLM can declare "
            "(skills with a version: line in SKILL.md frontmatter). "
            "Admin tool.",
            {"type": "object", "properties": {}, "additionalProperties": False},
        ),
        "arch_simulate": _tool(
            "arch_simulate",
            "Apply a counterfactual change (relation_add | move | "
            "delete) to a throwaway fork, evaluate the policy gate "
            "and fitness drift, and throw the fork away. The base "
            "world is byte-identical before and after — enforced as "
            "an internal assertion, not just a test. Admin tool.",
            {
                "type": "object",
                "properties": {
                    "verb": {
                        "type": "string",
                        "enum": ["relation_add", "move", "delete"],
                        "description": "What counterfactual to apply",
                    },
                    "source": {"type": "string"},
                    "target": {"type": "string"},
                    "kind": {"type": "string"},
                    "element": {"type": "string"},
                    "to": {"type": "string"},
                },
                "required": ["verb"],
                "additionalProperties": False,
            },
        ),
    }

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        tools = [
            _tool(
                "arch_get_status",
                "Return the project status envelope: snapshot, knowledge coverage, ledger.",
                {"type": "object", "properties": {}, "additionalProperties": False},
            ),
            _tool(
                "arch_get_explain",
                "Return evidence lineage for a subject (element, "
                "claim, observation or evidence id).",
                {
                    "type": "object",
                    "properties": {"subject": {"type": "string"}},
                    "required": ["subject"],
                    "additionalProperties": False,
                },
            ),
            _tool(
                "arch_search_code",
                "Search the code index by symbol or path prefix.",
                {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                    "additionalProperties": False,
                },
            ),
            _tool(
                "arch_get_context",
                "Compile a budgeted context pack from a goal string.",
                {
                    "type": "object",
                    "properties": {
                        "goal": {"type": "string"},
                        "subject": {"type": "string"},
                        "max_tokens": {"type": "integer", "minimum": 1, "maximum": 8192},
                    },
                    "required": ["goal"],
                    "additionalProperties": False,
                },
            ),
            _tool(
                "arch_get_history",
                "List run history summaries from the RunLedger.",
                {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "minimum": 1, "default": 50},
                        "status": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
            ),
        ]
        if admin:
            tools.extend(admin_tool_descriptors[t] for t in ADMIN_TOOLS)
        return tools

    def _world() -> tuple[ArchitectureWorld, CodeIndex | None]:
        world = ArchitectureWorld.for_repo(repo_path).open()
        index_path = world.workspace / "code.sqlite"
        index = CodeIndex(index_path).open() if index_path.exists() else None
        return world, index

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        # Admin gate: any tool name in the admin set MUST be refused
        # when admin is off, even if the client tries to call it
        # directly without listing first. We raise McpError so the
        # SDK marks isError=True on the wire; the envelope (with the
        # stable ADMIN_DISABLED code) is serialised as the message
        # so any consumer can parse it.
        if name in ADMIN_TOOLS and not admin:
            envelope = AdminDisabledError(f"tool {name!r} requires admin opt-in").to_envelope()
            raise McpError(ErrorData(code=-32603, message=json.dumps(envelope), data=envelope))
        # Read-only tools do not require admin: the gate above is
        # the only enforcement point. Calling require_admin(admin,
        # name) here would block the read-only tools, which is the
        # opposite of the documented behaviour.

        world, index = _world()
        try:
            if name == "arch_get_status":
                return _envelope(get_status(world, code_index=index).model_dump())
            if name == "arch_get_explain":
                try:
                    explanation = explain(world, arguments.get("subject", ""))
                except SubjectNotFound as exc:
                    return _envelope(
                        {
                            "code": exc.code,
                            "message": str(exc),
                            "subject": arguments.get("subject", ""),
                        }
                    )
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
                pack = compiler.compile(goal, subject=subject, budget=Budget(max_tokens=max_tokens))
                return _envelope(pack.model_dump())
            if name == "arch_get_history":
                limit = int(arguments.get("limit", 50))
                status = arguments.get("status")
                ledger = RunLedger()
                history = get_history(ledger, limit=limit, status=status)
                return _envelope(history.model_dump())
            if name == "arch_propose_list":
                return _envelope(_handle_admin_propose_list(arguments, world))
            if name == "arch_propose_create":
                return _envelope(
                    _call_proposals_handler(
                        handle_create,
                        world,
                        name=arguments["name"],
                        prompt_spec=arguments.get("prompt_spec"),
                        skill=list(arguments.get("skill") or []),
                    )
                )
            if name == "arch_propose_diff":
                return _envelope(
                    _call_proposals_handler(handle_diff, world, name=arguments["name"])
                )
            if name == "arch_propose_review":
                return _envelope(
                    _call_proposals_handler(
                        handle_review,
                        world,
                        name=arguments["name"],
                        min_coverage=arguments.get("min_coverage", 0.8),
                        max_unknowns=arguments.get("max_unknowns", 0),
                        max_findings=arguments.get("max_findings", 0),
                        max_run_age_days=arguments.get("max_run_age_days", 30),
                        require_pass=arguments.get("require_pass", False),
                    )
                )
            if name == "arch_propose_promote":
                return _envelope(
                    _call_proposals_handler(
                        handle_promote,
                        world,
                        name=arguments["name"],
                        approved_by=arguments["approved_by"],
                    )
                )
            if name == "arch_propose_reject":
                return _envelope(
                    _call_proposals_handler(
                        handle_reject, world, name=arguments["name"], actor=arguments["actor"]
                    )
                )
            if name == "arch_prompt_registry":
                return _envelope(_handle_admin_prompt_registry(arguments, world))
            if name == "arch_skill_registry":
                return _envelope(_handle_admin_skill_registry(arguments, world))
            if name == "arch_simulate":
                return _envelope(_handle_admin_simulate(arguments, world))
            return _envelope({"error": f"unknown tool {name!r}"})
        finally:
            if index is not None:
                index.close()
            world.close()

    return server


def handle(args: argparse.Namespace, world=None) -> int:
    repo_path = str(Path(args.repo).resolve())
    admin = bool(getattr(args, "admin", False)) or admin_enabled()
    server = build_server(repo_path, admin=admin)

    async def run() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    try:
        asyncio.run(run())
    except (KeyboardInterrupt, asyncio.CancelledError):
        return 0
    return 0
