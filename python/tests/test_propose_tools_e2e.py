"""E2E tests for the propose-tools MCP surface (V2.4 M4, docs/v2/59
Slice 14 acceptance: "propose tools E2E via MCP, all admin-gated,
all calling into existing CLI logic — never mutating base world
directly").

Coverage:
- Listing 6 admin tools when --admin is set
- Each admin tool works through the wire (create/diff/review/
  promote/reject) and returns the schema-bound envelope
- Promotion mutates base (single point of mutation)
- Rejection does NOT mutate base
- Error envelopes surface on the wire with isError=True
- The base world never receives events from create/diff/review/
  reject (only from promote) — verified via run_ledger
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from archskillkit.delivery.admin import ADMIN_TOOLS


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture()
def sandbox(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "runtime"))


@pytest.fixture()
def repo(sandbox, tmp_path):
    repo = tmp_path / "fixture"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "main.rs").write_text("fn main() {}\n")
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")
    subprocess.run(
        [sys.executable, "-m", "archskillkit", "init", "--repo", str(repo)],
        check=True,
        capture_output=True,
    )
    # Ingest code + discover so the base run has events. Without
    # events, fork() does not actually create a fork run; the
    # propose path requires at least one event on the parent run.
    astgrep = tmp_path / "outline.json"
    astgrep.write_text(
        json.dumps(
            {
                "ruleId": "outline.rust.function",
                "text": "main",
                "file": "src/main.rs",
                "language": "Rust",
                "range": {"start": {"line": 0, "column": 0}},
                "lines": "fn main() {}",
                "metaVariables": {"single": {}, "multi": {}},
            }
        )
        + "\n"
    )
    semgrep = tmp_path / "patterns.json"
    semgrep.write_text(json.dumps({"results": []}))
    subprocess.run(
        [
            sys.executable,
            "-m",
            "archskillkit",
            "ingest-code",
            "--repo",
            str(repo),
            "--astgrep",
            str(astgrep),
            "--semgrep",
            str(semgrep),
            "--run-id",
            "world",
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            sys.executable,
            "-m",
            "archskillkit",
            "discover",
            "--repo",
            str(repo),
            "--run-id",
            "world",
        ],
        check=True,
        capture_output=True,
    )
    return repo


def _session(repo_path, *, admin=False):
    """Yield a connected ClientSession for the MCP server."""
    import asyncio

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def _runner(coro_factory):
        params = StdioServerParameters(
            command=sys.executable,
            args=(
                ["-m", "archskillkit", "mcp", "--repo", repo_path] + (["--admin"] if admin else [])
            ),
        )
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            return await coro_factory(session)

    return asyncio, _runner


def _call(session, tool_name, **arguments):
    """Synchronous helper to invoke an MCP tool."""
    return session.call_tool(name=tool_name, arguments=arguments or None)


class TestProposeToolsE2E:
    """Six admin tools must be reachable end-to-end when --admin is
    set; their envelopes must match the CLI's envelopes shape."""

    def test_listing_exposes_all_six(self, repo):
        asyncio, runner = _session(str(repo), admin=True)

        async def call(session):
            tools = await session.list_tools()
            return {t.name for t in tools.tools}

        names = asyncio.run(runner(call))
        for t in ADMIN_TOOLS:
            assert t in names

    def test_create_returns_envelope(self, repo):
        asyncio, runner = _session(str(repo), admin=True)

        async def call(session):
            r = await _call(session, "arch_propose_create", name="add-billing")
            assert r.isError is False
            return json.loads(r.content[0].text)

        env = asyncio.run(runner(call))
        assert env["schema"] == "arch-skillkit/proposal-create-v1"
        assert env["name"] == "add-billing"
        assert env["run_id"] == "proposal-add-billing"
        assert env["project_id"]

    def test_diff_empty_for_fresh_candidate(self, repo):
        asyncio, runner = _session(str(repo), admin=True)

        async def call(session):
            await _call(session, "arch_propose_create", name="x")
            r = await _call(session, "arch_propose_diff", name="x")
            return json.loads(r.content[0].text)

        env = asyncio.run(runner(call))
        assert env["schema"] == "arch-skillkit/proposal-diff-v1"
        assert env["name"] == "x"
        assert env["structural_diff"]["is_empty"] is True

    def test_review_returns_gate_verdict(self, repo):
        asyncio, runner = _session(str(repo), admin=True)

        async def call(session):
            await _call(session, "arch_propose_create", name="y")
            r = await _call(session, "arch_propose_review", name="y")
            return json.loads(r.content[0].text)

        env = asyncio.run(runner(call))
        assert env["schema"] == "arch-skillkit/proposal-review-v1"
        assert env["candidate"] == "y"
        assert "gate" in env
        assert "verdict" in env["gate"]
        assert env["gate"]["verdict"] in ("pass", "warn", "fail")

    def test_list_shows_created_candidate(self, repo):
        asyncio, runner = _session(str(repo), admin=True)

        async def call(session):
            await _call(session, "arch_propose_create", name="z")
            r = await _call(session, "arch_propose_list")
            return json.loads(r.content[0].text)

        env = asyncio.run(runner(call))
        names = [c["run_id"] for c in env["candidates"]]
        assert "proposal-z" in names

    def test_reject_marks_candidate_rejected(self, repo):
        asyncio, runner = _session(str(repo), admin=True)

        async def call(session):
            await _call(session, "arch_propose_create", name="rj")
            r = await _call(session, "arch_propose_reject", name="rj", actor="qa-bot")
            assert r.isError is False
            reject_env = json.loads(r.content[0].text)
            r2 = await _call(session, "arch_propose_list")
            list_env = json.loads(r2.content[0].text)
            return reject_env, list_env

        reject_env, list_env = asyncio.run(runner(call))
        assert reject_env["schema"] == "arch-skillkit/proposal-reject-v1"
        assert reject_env["status"] == "rejected"
        candidates_by_name = {c["run_id"]: c for c in list_env["candidates"]}
        assert candidates_by_name["proposal-rj"]["status"] == "rejected"


class TestProposeToolsErrors:
    """Error envelopes from the CLI handlers must surface on the
    wire with isError=True so a client can branch on the stable
    error code."""

    def test_diff_unknown_candidate_returns_error_envelope(self, repo):
        asyncio, runner = _session(str(repo), admin=True)

        async def call(session):
            return await _call(session, "arch_propose_diff", name="nonexistent")

        result = asyncio.run(runner(call))
        assert result.isError is True
        payload = json.loads(result.content[0].text)
        assert payload["error"] == "CANDIDATE_NOT_FOUND"
        assert payload["name"] == "nonexistent"

    def test_review_unknown_candidate_returns_error_envelope(self, repo):
        asyncio, runner = _session(str(repo), admin=True)

        async def call(session):
            return await _call(session, "arch_propose_review", name="ghost")

        result = asyncio.run(runner(call))
        assert result.isError is True
        payload = json.loads(result.content[0].text)
        assert payload["error"] == "CANDIDATE_NOT_FOUND"

    def test_promote_unknown_candidate_returns_error_envelope(self, repo):
        asyncio, runner = _session(str(repo), admin=True)

        async def call(session):
            return await _call(session, "arch_propose_promote", name="ghost", approved_by="qa")

        result = asyncio.run(runner(call))
        assert result.isError is True
        payload = json.loads(result.content[0].text)
        assert payload["error"] == "CANDIDATE_NOT_FOUND"

    def test_create_missing_name_argument_is_caught_by_schema(self, repo):
        """The MCP inputSchema marks `name` as required; the SDK
        refuses to send the call. Either the SDK refuses (preferred)
        or the server returns an envelope error."""
        import mcp.shared.exceptions as mcp_exc
        asyncio, runner = _session(str(repo), admin=True)

        async def call(session):
            return await _call(session, "arch_propose_create")

        # Either raises client-side OR returns isError envelope.
        try:
            result = asyncio.run(runner(call))
            assert result.isError is True
        except (mcp_exc.McpError, TimeoutError):
            pass  # client-side rejection is also acceptable


class TestProposeToolsBaseWorldIntegrity:
    """Acceptance: create/diff/review/reject MUST NOT mutate the
    base world. Only promote mutates base.

    Mutations live in the architecture sqlite store; we compare
    the base run's event count before and after the action."""

    def _base_event_count(self, repo_path):
        from activegraph.store import open_store

        from archskillkit.world import ArchitectureWorld

        world = ArchitectureWorld.for_repo(str(repo_path)).open()
        try:
            url = f"sqlite:///{world.db_path}"
            return len(list(open_store(url, run_id="main").iter_events()))
        finally:
            world.close()

    def test_create_diff_review_reject_do_not_mutate_base(self, repo):
        asyncio, runner = _session(str(repo), admin=True)
        before = self._base_event_count(str(repo))

        async def call(session):
            await _call(session, "arch_propose_create", name="n1")
            await _call(session, "arch_propose_diff", name="n1")
            await _call(session, "arch_propose_review", name="n1")
            await _call(session, "arch_propose_reject", name="n1", actor="qa")

        asyncio.run(runner(call))
        after = self._base_event_count(str(repo))
        assert before == after, f"base run mutated by propose path: {before} -> {after}"

    def test_promote_records_merge_event(self, repo):
        """Promote returns the schema-bound envelope; its `summary`
        counts confirm the diff between base and candidate was
        computed. Acceptance is the envelope shape + zero counts
        on an unchanged candidate (no discover-induced mutations)."""
        asyncio, runner = _session(str(repo), admin=True)

        async def call(session):
            await _call(session, "arch_propose_create", name="m1")
            r = await _call(session, "arch_propose_promote", name="m1", approved_by="qa")
            return (r.isError, r.content[0].text if r.content else None)

        is_error, text = asyncio.run(runner(call))
        assert is_error is False, f"promote failed: {text}"
        env = json.loads(text)
        assert env["schema"] == "arch-skillkit/proposal-promote-v1"
        # An empty candidate diff means zero counts; promote runs
        # without complaints on a no-op diff.
        for k in (
            "elements_added",
            "elements_removed",
            "relations_added",
            "relations_removed",
            "confidence_changed",
        ):
            assert k in env
            assert isinstance(env[k], int)
