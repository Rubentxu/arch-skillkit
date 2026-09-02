"""Admin gate (V2.4 M4, docs/v2/59 M4 acceptance: "admin disabled by
default").

Gates:
- default: read-only tools exposed; admin tools hidden AND any
  call to an admin tool returns the stable ADMIN_DISABLED code
- ARCH_SKILLKIT_ADMIN=1 or --admin CLI flag enables admin tools
- arch_propose_list (admin tool) returns the candidates list when
  enabled; same call returns ADMIN_DISABLED when disabled
- AdminDisabledError.to_envelope emits the stable code so any
  delivery adapter can reuse the same refusal shape
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from archskillkit.delivery.admin import (
    ADMIN_DISABLED_CODE,
    ADMIN_TOOLS,
    AdminDisabledError,
    admin_enabled,
    require_admin,
)


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture()
def sandbox(monkeypatch, tmp_path):
    data = tmp_path / "data"
    monkeypatch.setenv("XDG_DATA_HOME", str(data))
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
    return repo


class TestAdminGatePure:
    def test_admin_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("ARCH_SKILLKIT_ADMIN", raising=False)
        assert admin_enabled() is False
        assert admin_enabled(cli_flag=False) is False

    @pytest.mark.parametrize("value", ["1", "true", "yes", "TRUE", "Yes"])
    def test_admin_enabled_by_env_truthy(self, monkeypatch, value):
        monkeypatch.setenv("ARCH_SKILLKIT_ADMIN", value)
        assert admin_enabled() is True

    def test_admin_enabled_by_cli_flag(self, monkeypatch):
        monkeypatch.delenv("ARCH_SKILLKIT_ADMIN", raising=False)
        assert admin_enabled(cli_flag=True) is True

    def test_require_admin_raises_when_disabled(self):
        with pytest.raises(AdminDisabledError) as excinfo:
            require_admin(False, "arch_propose_list")
        assert excinfo.value.code == ADMIN_DISABLED_CODE

    def test_require_admin_quiet_when_enabled(self):
        require_admin(True, "arch_propose_list")  # no raise

    def test_envelope_shape(self):
        env = AdminDisabledError("nope").to_envelope()
        assert env["code"] == ADMIN_DISABLED_CODE
        assert "nope" in env["message"]


class TestAdminGateE2E:
    def _session(self, repo_path, *, admin=False):
        import asyncio

        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        async def _runner(coro_factory):
            params = StdioServerParameters(
                command=sys.executable,
                args=(
                    ["-m", "archskillkit", "mcp", "--repo", repo_path]
                    + (["--admin"] if admin else [])
                ),
            )
            async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
                await session.initialize()
                return await coro_factory(session)

        return asyncio, _runner

    def test_admin_tool_hidden_when_disabled(self, repo):
        asyncio, runner = self._session(str(repo), admin=False)

        async def call(session):
            tools = await session.list_tools()
            return {t.name for t in tools.tools}

        names = asyncio.run(runner(call))
        for admin_tool in ADMIN_TOOLS:
            assert admin_tool not in names

    def test_admin_tool_listed_when_enabled(self, repo):
        asyncio, runner = self._session(str(repo), admin=True)

        async def call(session):
            tools = await session.list_tools()
            return {t.name for t in tools.tools}

        names = asyncio.run(runner(call))
        for admin_tool in ADMIN_TOOLS:
            assert admin_tool in names

    def test_admin_tool_call_refused_when_disabled(self, repo):
        """End-to-end: when admin is disabled, calling an admin
        tool returns a CallToolResult with isError=True and the
        ADMIN_DISABLED envelope in the text content."""
        asyncio, runner = self._session(str(repo), admin=False)

        async def call(session):
            return await session.call_tool("arch_propose_list", {})

        result = asyncio.run(runner(call))
        assert result.isError is True
        payload = json.loads(result.content[0].text)
        assert payload["code"] == ADMIN_DISABLED_CODE

    def test_admin_tool_works_when_enabled(self, repo):
        asyncio, runner = self._session(str(repo), admin=True)

        async def call(session):
            r = await session.call_tool("arch_propose_list", {})
            return r.content[0].text, r.isError

        text, is_error = asyncio.run(runner(call))
        payload = json.loads(text)
        assert payload["schema"] == "arch-skillkit/proposals-list-v1"
        assert "candidates" in payload
        assert is_error is False

    def test_admin_via_env_var_without_cli_flag(self, repo, monkeypatch):
        """Setting ARCH_SKILLKIT_ADMIN=1 alone must enable admin tools
        even when --admin is not passed on the CLI."""
        import asyncio

        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        async def call(session):
            tools = await session.list_tools()
            return {t.name for t in tools.tools}

        env = os.environ.copy()
        env["ARCH_SKILLKIT_ADMIN"] = "1"
        env["XDG_DATA_HOME"] = str(repo.parent / "data")
        env["XDG_STATE_HOME"] = str(repo.parent / "state")
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "archskillkit", "mcp", "--repo", str(repo)],
            env=env,
        )

        async def runner():
            async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
                await session.initialize()
                return await call(session)

        names = asyncio.run(runner())
        for admin_tool in ADMIN_TOOLS:
            assert admin_tool in names

    def test_server_side_gate_via_unit(self, repo):
        """Drive build_server directly so the server-side gate
        (defence in depth) is exercised even though the client SDK
        would normally refuse unlisted tool calls."""
        import asyncio

        from mcp.types import CallToolRequest, CallToolRequestParams

        from archskillkit.delivery.cli.mcp import build_server

        server = build_server(str(repo), admin=False)
        handler = server.request_handlers[CallToolRequest]
        req = CallToolRequest(params=CallToolRequestParams(name="arch_propose_list", arguments={}))

        async def call_handler():
            return await handler(req)

        result = asyncio.run(call_handler())
        assert result.root.isError is True
        payload = json.loads(result.root.content[0].text)
        assert payload["code"] == ADMIN_DISABLED_CODE
