"""V2.4 M4 slice 18 — counterfactual simulate.

Covers docs/v2/57 §7-§8 (SimulationResult schema, recommendation
verb) and the UAT24-044 contract that ``simulate`` does not mutate
the base world.

Three test classes:

* TestSimulationBaseInvariant: base world byte-identical before and
  after simulate (allowed, blocked, error cases).
* TestSimulationVerbs: each verb (relation_add, move, delete) is
  applied to the fork and never to the base.
* TestSimulationMCP: the admin tool ``arch_simulate`` is reachable
  end-to-end via MCP stdio, refuses without --admin, and returns the
  same envelope shape as the CLI.

The test fixtures use a tiny Rust repo plus two architecture elements
seeded via ``world.add_architecture_element`` (inside ``with world:``
so the writes commit). The simulator does the rest.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# ---- fixtures ---------------------------------------------------------------


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    """Tiny repo with init + ingest + discover, plus 3 elements.

    Routes XDG_DATA_HOME / XDG_STATE_HOME under ``tmp_path`` so the
    test does not pollute the host home. Three elements are
    seeded (``foo``, ``bar``, ``qux``) so every verb has at least
    one valid target.
    """
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
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
    _seed_elements(repo)
    return repo


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _seed_elements(repo: Path) -> None:
    """Add three elements to the base world so every verb has
    valid targets. Runs through the CLI so the writes commit."""
    code = (
        "from archskillkit.world import ArchitectureWorld\n"
        "world = ArchitectureWorld.for_repo(REPO).open()\n"
        "with world:\n"
        "    world.add_architecture_element('foo', 'component')\n"
        "    world.add_architecture_element('bar', 'component')\n"
        "    world.add_architecture_element('qux', 'external_system')\n"
        "world.close()\n"
    ).replace("REPO", repr(str(repo)))
    subprocess.run([sys.executable, "-c", code], check=True, capture_output=True)


def _run_simulate(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "archskillkit", "simulate", "--repo", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _world(repo: Path):
    from archskillkit.world import ArchitectureWorld

    return ArchitectureWorld.for_repo(str(repo)).open()


# ---- base-invariance -------------------------------------------------------


class TestSimulationBaseInvariant:
    """UAT24-044: simulate must leave the base world byte-identical."""

    def test_relation_add_does_not_mutate_base(self, repo):
        before = _world(repo)
        before_digest = before.snapshot()
        before.close()
        res = _run_simulate(repo, "relation", "add", "foo", "bar")
        assert res.returncode == 0, res.stderr
        after = _world(repo)
        after_digest = after.snapshot()
        # Base objects unchanged, no new relations, no new runs.
        assert after_digest == before_digest
        assert after.architecture_relations() == []
        # Throwaway fork dropped: only the main run survives.
        assert after.list_runs() == ["world"]
        after.close()

    def test_delete_does_not_mutate_base(self, repo):
        before = _world(repo)
        before_digest = before.snapshot()
        before.close()
        res = _run_simulate(repo, "delete", "foo")
        assert res.returncode == 0, res.stderr
        after = _world(repo)
        after_digest = after.snapshot()
        assert after_digest == before_digest
        # foo is still in the base world.
        assert bool(after.find_objects("architecture_element", name="foo"))
        assert after.list_runs() == ["world"]
        after.close()

    def test_move_does_not_mutate_base(self, repo):
        before = _world(repo)
        before_digest = before.snapshot()
        before.close()
        res = _run_simulate(repo, "move", "foo", "--to", "bounded_context")
        assert res.returncode == 0, res.stderr
        after = _world(repo)
        after_digest = after.snapshot()
        assert after_digest == before_digest
        # foo is still a component in the base world.
        foo = after.find_objects("architecture_element", name="foo")
        assert foo[0]["data"]["kind"] == "component"
        after.close()

    def test_envelope_carries_matching_base_digests(self, repo):
        res = _run_simulate(repo, "relation", "add", "foo", "bar")
        envelope = json.loads(res.stdout)
        assert envelope["base_unchanged"] is True
        assert envelope["base_snapshot_id"] == envelope["base_snapshot_after_id"]


# ---- verb behaviour --------------------------------------------------------


class TestSimulationVerbs:
    """Each verb: applies to fork, surfaces recommendation, cleans up."""

    def test_relation_add_succeeds(self, repo):
        res = _run_simulate(repo, "relation", "add", "foo", "bar", "--kind", "calls")
        assert res.returncode == 0
        env = json.loads(res.stdout)
        assert env["verb"] == "relation_add"
        assert env["applied_to_fork"]["source"] == "foo"
        assert env["applied_to_fork"]["target"] == "bar"
        assert env["applied_to_fork"]["kind"] == "calls"
        assert env["applied_to_fork"]["relation_id"].startswith("rel_")
        assert env["base_unchanged"] is True

    def test_move_succeeds(self, repo):
        res = _run_simulate(repo, "move", "foo", "--to", "bounded_context")
        assert res.returncode == 0, res.stderr
        env = json.loads(res.stdout)
        assert env["verb"] == "move"
        assert env["applied_to_fork"]["element"] == "foo"
        assert env["applied_to_fork"]["to"] == "bounded_context"
        assert env["base_unchanged"] is True

    def test_delete_succeeds(self, repo):
        res = _run_simulate(repo, "delete", "bar")
        assert res.returncode == 0, res.stderr
        env = json.loads(res.stdout)
        assert env["verb"] == "delete"
        assert env["applied_to_fork"]["element"] == "bar"
        assert env["base_unchanged"] is True

    def test_unknown_element_returns_stable_error(self, repo):
        res = _run_simulate(repo, "delete", "ghost")
        assert res.returncode == 1
        env = json.loads(res.stderr)
        assert env["schema"] == "arch-skillkit/simulation-result-v1"
        assert env["error"] == "ELEMENT_NOT_FOUND"
        assert "ghost" in env["message"]

    def test_invalid_category_returns_stable_error(self, repo):
        res = _run_simulate(repo, "move", "foo", "--to", "not_a_category")
        assert res.returncode == 1
        env = json.loads(res.stderr)
        assert env["error"] == "INVALID_CATEGORY"

    def test_recommendation_is_one_of_four(self, repo):
        """Recommendation must be a stable enum value (UAT24-044)."""
        for verb, args in [
            ("relation", ["add", "foo", "bar"]),
            ("delete", ["foo"]),
            ("move", ["foo", "--to", "bounded_context"]),
        ]:
            res = _run_simulate(repo, verb, *args)
            assert res.returncode == 0
            env = json.loads(res.stdout)
            assert env["recommendation"] in ("allowed", "risky", "blocked", "unknown")


# ---- MCP admin tool --------------------------------------------------------


class TestSimulationMCP:
    """The admin tool ``arch_simulate`` is reachable end-to-end via
    MCP stdio, refuses without --admin, and returns the same envelope
    shape as the CLI."""

    def _session(self, repo_path, *, admin):
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
                env=os.environ.copy(),
            )
            async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
                await session.initialize()
                return await coro_factory(session)

        return asyncio, _runner

    def test_tool_listed_only_with_admin(self, repo):
        import asyncio

        from archskillkit.delivery.admin import ADMIN_TOOLS

        async def names(s, runner):
            async def call(sess):
                return {t.name for t in (await sess.list_tools()).tools}

            return await runner(call)

        async def main():
            _, runner_off = self._session(str(repo), admin=False)
            _, runner_on = self._session(str(repo), admin=True)
            return (
                await names(None, runner_off),
                await names(None, runner_on),
            )

        without, with_admin = asyncio.run(main())
        assert "arch_simulate" not in without
        assert "arch_simulate" in with_admin
        assert "arch_simulate" in ADMIN_TOOLS

    def test_simulate_via_mcp_returns_envelope(self, repo):
        asyncio_, runner = self._session(str(repo), admin=True)

        async def call(session):
            return await session.call_tool(
                name="arch_simulate",
                arguments={
                    "verb": "relation_add",
                    "source": "foo",
                    "target": "bar",
                    "kind": "calls",
                },
            )

        result = asyncio_.run(runner(call))
        assert result.isError is False
        env = json.loads(result.content[0].text)
        assert env["verb"] == "relation_add"
        assert env["base_unchanged"] is True
        assert env["base_snapshot_id"] == env["base_snapshot_after_id"]

    def test_simulate_via_mcp_refused_without_admin(self, repo):
        asyncio_, runner = self._session(str(repo), admin=False)

        async def call(session):
            return await session.call_tool(
                name="arch_simulate",
                arguments={"verb": "delete", "element": "foo"},
            )

        result = asyncio_.run(runner(call))
        assert result.isError is True
        env = json.loads(result.content[0].text)
        assert env["code"] == "ADMIN_DISABLED"

    def test_simulate_via_mcp_unknown_element(self, repo):
        asyncio_, runner = self._session(str(repo), admin=True)

        async def call(session):
            return await session.call_tool(
                name="arch_simulate",
                arguments={"verb": "delete", "element": "ghost"},
            )

        result = asyncio_.run(runner(call))
        assert result.isError is True
        env = json.loads(result.content[0].text)
        assert env["error"] == "ELEMENT_NOT_FOUND"
