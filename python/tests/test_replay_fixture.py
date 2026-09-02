"""Replay-fixture V2.4 M4 slice 19 (docs/v2/58 gate "replay fixture
without API key").

Three angles:

  1. Determinism — replaying the same captured payload twice yields
     the same stable digest. We bypass any wall-clock-sensitive
     fields by hashing over code/policy/knowledge/event_id only
     (see ``replay_fixture._stable_digest``).

  2. Drift detection — when the live pipeline produces a different
     stable digest from the golden, the CLI exits 1 and the
     envelope carries the comparison under the ``drift`` key.

  3. MCP reach — ``arch_replay_fixture`` is listed without --admin
     and returns the same envelope as the CLI subprocess. Errors
     (missing fixture) come back as McpError with the stable
     ``FIXTURE_MISSING`` code.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "replay" / "kotlin-demo"


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "archskillkit", "replay-fixture", *args],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture()
def fixture_dir(tmp_path, monkeypatch):
    """Copy the bundled Kotlin fixture to a writable tmp dir so we can
    freely rewrite golden.json without touching the source tree."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    dst = tmp_path / "kotlin-demo"
    shutil.copytree(FIXTURE_DIR, dst)
    return dst


# ---- Determinism ---------------------------------------------------------


def test_replay_is_deterministic(fixture_dir):
    cp1 = _run_cli(str(fixture_dir), "--write-golden")
    assert cp1.returncode == 0, cp1.stdout + cp1.stderr
    payload1 = json.loads(cp1.stdout)
    digest1 = payload1["replayed_snapshot_id"]

    cp2 = _run_cli(str(fixture_dir))
    assert cp2.returncode == 0, cp2.stdout + cp2.stderr
    digest2 = json.loads(cp2.stdout)["replayed_snapshot_id"]

    cp3 = _run_cli(str(fixture_dir))
    assert cp3.returncode == 0, cp3.stdout + cp3.stderr
    digest3 = json.loads(cp3.stdout)["replayed_snapshot_id"]

    assert digest1 == digest2 == digest3
    assert payload1["match"] is True
    assert payload1["drift"] is None


def test_replay_first_run_writes_golden(fixture_dir):
    """Without --write-golden, a fresh fixture exits 1 with
    'no golden.json present'. With --write-golden, exits 0 and
    materialises golden.json."""
    if (fixture_dir / "golden.json").exists():
        (fixture_dir / "golden.json").unlink()

    cp = _run_cli(str(fixture_dir))
    assert cp.returncode == 1
    payload = json.loads(cp.stdout)
    assert payload["match"] is False
    assert "no golden.json present" in payload["drift"]["reason"]

    cp_write = _run_cli(str(fixture_dir), "--write-golden")
    assert cp_write.returncode == 0
    assert (fixture_dir / "golden.json").exists()

    cp_check = _run_cli(str(fixture_dir))
    assert cp_check.returncode == 0


# ---- Drift detection -----------------------------------------------------


def test_drift_when_golden_tampered(fixture_dir):
    """A golden with a wrong snapshot_id is detected: envelope carries
    the comparison, exit code is 1, the CLI never lies about success."""
    _run_cli(str(fixture_dir), "--write-golden")

    golden = fixture_dir / "golden.json"
    raw = json.loads(golden.read_text())
    raw["snapshot_id"] = "a" * 64
    golden.write_text(json.dumps(raw, indent=2))

    cp = _run_cli(str(fixture_dir))
    assert cp.returncode == 1
    payload = json.loads(cp.stdout)
    assert payload["match"] is False
    assert payload["drift"] is not None
    assert payload["drift"]["replayed"]["snapshot_id"] != payload["drift"]["golden"]["snapshot_id"]


def test_drift_when_payload_mutated(fixture_dir):
    """When the captured scanner payload changes, the replay must
    detect it. Renaming the file ``path`` in one semgrep result
    drops one symbol + edge from the code index; the replay must
    surface that as a stable-digest mismatch (and therefore as
    a FIXTURE_DRIFT in CI)."""
    _run_cli(str(fixture_dir), "--write-golden")

    semgrep = fixture_dir / "payloads" / "semgrep.json"
    raw_text = semgrep.read_text()
    # The "path" field is what the scanner uses to resolve the
    # containing symbol; renaming it shifts the symbol set the
    # code index ingests (an unresolvable match becomes a warning
    # and is skipped). check_id, by contrast, is just a rule label
    # and does NOT affect the ingest — we tested that explicitly.
    semgrep.write_text(raw_text.replace('"path": "kotlin-spring', '"path": "kotlin-x-spring', 1))

    cp = _run_cli(str(fixture_dir))
    assert cp.returncode == 1
    payload = json.loads(cp.stdout)
    assert payload["match"] is False


def test_strict_flag_returns_2_on_drift(fixture_dir):
    """``--strict`` is the CI-friendly contract: drift -> exit 2 so
    pipelines can distinguish drift from a missing-fixture (exit 1)."""
    _run_cli(str(fixture_dir), "--write-golden")

    golden = fixture_dir / "golden.json"
    raw = json.loads(golden.read_text())
    raw["policy_revision"] = "tampered"
    golden.write_text(json.dumps(raw, indent=2))

    cp = _run_cli(str(fixture_dir), "--strict")
    assert cp.returncode == 2
    payload = json.loads(cp.stdout)
    assert payload["match"] is False
    assert payload["drift"]["policy_revision_drift"] is True


def test_missing_payload_returns_fixture_missing(fixture_dir):
    """A fixture without payload.json is rejected with a stable
    FIXTURE_MISSING code, not a stack trace."""
    (fixture_dir / "payload.json").unlink()

    cp = _run_cli(str(fixture_dir))
    assert cp.returncode == 1
    payload = json.loads(cp.stderr)
    assert payload["error"] == "FIXTURE_MISSING"


# ---- MCP integration -----------------------------------------------------


def test_arch_replay_fixture_via_mcp(tmp_path, monkeypatch):
    """``arch_replay_fixture`` is listed in read-only tools without
    --admin and returns the same envelope as the CLI subprocess."""
    import asyncio

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    # Sandbox repo so MCP has something to bind to (replay does not
    # need it, but the MCP server requires --repo).
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    sandbox_repo = tmp_path / "demo"
    sandbox_repo.mkdir()
    subprocess.run(["git", "-C", str(sandbox_repo), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(sandbox_repo), "config", "user.email", "r@r"], check=True)
    subprocess.run(["git", "-C", str(sandbox_repo), "config", "user.name", "r"], check=True)
    subprocess.run(
        [sys.executable, "-m", "archskillkit", "init", "--repo", str(sandbox_repo)],
        check=True,
        capture_output=True,
    )

    fixture_copy = tmp_path / "kotlin-demo"
    shutil.copytree(FIXTURE_DIR, fixture_copy)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "archskillkit",
            "replay-fixture",
            str(fixture_copy),
            "--write-golden",
        ],
        check=True,
        capture_output=True,
    )

    async def runner(coro_factory):
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "archskillkit", "mcp", "--repo", str(sandbox_repo)],
        )
        async with stdio_client(params) as (read, write), ClientSession(read, write) as s:
            await s.initialize()
            return await coro_factory(s)

    async def main():
        async def call(s):
            return await s.call_tool(
                "arch_replay_fixture",
                {"fixture_dir": str(fixture_copy)},
            )

        return await runner(call)

    result = asyncio.run(main())
    assert result.isError is False, result.content
    payload = json.loads(result.content[0].text)
    assert payload["schema"] == "arch-skillkit/replay-fixture-result-v1"
    assert payload["match"] is True


def test_arch_replay_fixture_listed_without_admin(tmp_path, monkeypatch):
    """The tool is part of the read-only tier and is listed without
    ``--admin`` — no need to opt in to use it."""
    import asyncio

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    sandbox_repo = tmp_path / "demo"
    sandbox_repo.mkdir()
    subprocess.run(["git", "-C", str(sandbox_repo), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(sandbox_repo), "config", "user.email", "r@r"], check=True)
    subprocess.run(["git", "-C", str(sandbox_repo), "config", "user.name", "r"], check=True)
    subprocess.run(
        [sys.executable, "-m", "archskillkit", "init", "--repo", str(sandbox_repo)],
        check=True,
        capture_output=True,
    )

    async def runner(coro_factory):
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "archskillkit", "mcp", "--repo", str(sandbox_repo)],
        )
        async with stdio_client(params) as (read, write), ClientSession(read, write) as s:
            await s.initialize()
            return await coro_factory(s)

    async def main():
        async def call(s):
            return {t.name for t in (await s.list_tools()).tools}

        return await runner(call)

    names = asyncio.run(main())
    assert "arch_replay_fixture" in names
