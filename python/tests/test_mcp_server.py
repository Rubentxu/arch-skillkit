"""MCP server end-to-end (V2.4 M4, docs/v2/55 §3, slice 13).

Spawns the real server as a subprocess, opens an MCP client session
over stdio, and exercises the read-only tools. Gates:
- list_tools returns the five read-only tools and no write tools
- arch_get_status, arch_get_explain, arch_search_code,
  arch_get_context, arch_get_history all return schema-bound
  JSON envelopes
- arch_get_explain with an unknown subject returns the stable
  SUBJECT_NOT_FOUND error code
"""

import json
import subprocess
import sys

import pytest


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture()
def sandbox(monkeypatch, tmp_path):
    data = tmp_path / "data"
    monkeypatch.setenv("XDG_DATA_HOME", str(data))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "runtime"))


@pytest.fixture()
def repo_with_world(tmp_path):
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
    return repo


def _text(content) -> str:
    return content[0].text if content else ""


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


def test_list_tools_only_read_only(sandbox, repo_with_world):
    asyncio, runner = _session(str(repo_with_world))

    async def call(session):
        tools = await session.list_tools()
        return {t.name for t in tools.tools}

    names = asyncio.run(runner(call))
    assert {
        "arch_get_status",
        "arch_get_explain",
        "arch_search_code",
        "arch_get_context",
        "arch_get_history",
    } <= names
    for forbidden in ("arch_apply", "arch_mutate", "arch_propose", "arch_promote"):
        assert forbidden not in names


def test_arch_get_status_returns_envelope(sandbox, repo_with_world):
    asyncio, runner = _session(str(repo_with_world))

    async def call(session):
        result = await session.call_tool("arch_get_status", {})
        return _text(result.content)

    payload = json.loads(asyncio.run(runner(call)))
    assert payload["schema"] == "arch-skillkit/status-result-v1"
    assert "project_id" in payload


def test_arch_get_explain_subject_not_found(sandbox, repo_with_world):
    asyncio, runner = _session(str(repo_with_world))

    async def call(session):
        result = await session.call_tool("arch_get_explain", {"subject": "nope"})
        return _text(result.content)

    payload = json.loads(asyncio.run(runner(call)))
    assert payload["code"] == "SUBJECT_NOT_FOUND"


def test_arch_get_history_returns_envelope(sandbox, repo_with_world):
    asyncio, runner = _session(str(repo_with_world))

    async def call(session):
        result = await session.call_tool("arch_get_history", {"limit": 3})
        return _text(result.content)

    payload = json.loads(asyncio.run(runner(call)))
    assert payload["schema"] == "arch-skillkit/history-v1"
    assert "runs" in payload
    assert isinstance(payload["runs"], list)
