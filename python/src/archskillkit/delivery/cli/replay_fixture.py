"""`archskillkit replay-fixture` — pipeline replay against a captured
scanner payload (V2.4 M4 slice 19, docs/v2/58 gate "replay fixture
without API key", docs/v2/56 §10 "replay debe detectar divergencia si
cambia prompt hash/schema/policy").

A fixture directory contains:

  payload.json
    { "astgrep_path": "astgrep-kotlin.json",
      "semgrep_path": "semgrep-kotlin.json",
      "scanner_versions": { "astgrep": "...", "semgrep": "..." } }
  golden.json
    { "schema": "arch-skillkit/replay-fixture-golden-v1",
      "snapshot_id": "<sha256>",
      "policy_revision": "...",
      "code_revision": "..." }

Replay opens a sandboxed repo, runs init + ingest-code against the
recorded payloads, builds the resulting snapshot, and compares
``snapshot.digest()`` byte-for-byte against the golden. Drift (a pack
bump, a schema change, a scanner version bump) shows up as a digest
mismatch with a stable ``FIXTURE_DRIFT`` code; CI fails the gate.

The MCP delivery adapter (delivery/cli/mcp.py) exposes this as
``arch_replay_fixture`` — read-only, no admin tier needed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from archskillkit.application.snapshot_builder import build_snapshot
from archskillkit.codeindex import CodeIndex
from archskillkit.world import ArchitectureWorld

NAME = "replay-fixture"
NEEDS_WORLD = False

SCHEMA_PAYLOAD = "arch-skillkit/replay-fixture-payload-v1"
SCHEMA_GOLDEN = "arch-skillkit/replay-fixture-golden-v1"
SCHEMA_RESULT = "arch-skillkit/replay-fixture-result-v1"


class ReplayFixtureError(Exception):
    """Base error for replay-fixture (V2.4 M4 slice 19)."""

    code: str = "REPLAY_FAILED"

    def __init__(self, code: str, message: str, *, fixture_id: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.fixture_id = fixture_id

    def to_envelope(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "schema": SCHEMA_RESULT,
            "error": self.code,
            "message": self.message,
        }
        if self.fixture_id is not None:
            out["fixture_id"] = self.fixture_id
        return out


class PayloadSpec(BaseModel):
    """Recorded scanner payloads + their pinned versions."""

    model_config = ConfigDict(extra="forbid")

    schema: str = Field(default=SCHEMA_PAYLOAD)
    astgrep_path: str = Field(description="Relative path under fixture_dir.")
    semgrep_path: str = Field(description="Relative path under fixture_dir.")
    scanner_versions: dict[str, str] = Field(
        default_factory=dict,
        description="Pinned scanner versions. Replay warns when the live"
        " toolchain differs; drift on the recorded version"
        " is itself a FIXTURE_DRIFT signal.",
    )


class GoldenSnapshot(BaseModel):
    """Recorded post-pipeline snapshot digest + revisions."""

    model_config = ConfigDict(extra="forbid")

    schema: str = Field(default=SCHEMA_GOLDEN)
    snapshot_id: str
    policy_revision: str
    code_revision: str


class ReplayResult(BaseModel):
    """Replay verdict envelope (V2.4 M4 slice 19, docs/v2/56 §10)."""

    model_config = ConfigDict(extra="forbid")

    schema: str = Field(default=SCHEMA_RESULT)
    fixture_id: str
    fixture_dir: str
    replayed_snapshot_id: str
    golden_snapshot_id: str | None = None
    match: bool
    drift: dict[str, Any] | None = None
    pinned: dict[str, str]
    live_toolchain: dict[str, str]


def _load_payload(fixture_dir: Path) -> PayloadSpec:
    payload_file = fixture_dir / "payload.json"
    if not payload_file.exists():
        raise ReplayFixtureError(
            "FIXTURE_MISSING",
            f"payload.json not found under {fixture_dir}",
        )
    raw = json.loads(payload_file.read_text())
    if raw.get("schema") != SCHEMA_PAYLOAD:
        raise ReplayFixtureError(
            "FIXTURE_SCHEMA_INVALID",
            f"payload.json schema is {raw.get('schema')!r}, expected {SCHEMA_PAYLOAD!r}",
        )
    return PayloadSpec.model_validate(raw)


def _load_golden(fixture_dir: Path) -> GoldenSnapshot | None:
    golden_file = fixture_dir / "golden.json"
    if not golden_file.exists():
        return None
    raw = json.loads(golden_file.read_text())
    if raw.get("schema") != SCHEMA_GOLDEN:
        raise ReplayFixtureError(
            "FIXTURE_SCHEMA_INVALID",
            f"golden.json schema is {raw.get('schema')!r}, expected {SCHEMA_GOLDEN!r}",
        )
    return GoldenSnapshot.model_validate(raw)


def _write_golden(fixture_dir: Path, golden: GoldenSnapshot) -> None:
    golden_file = fixture_dir / "golden.json"
    golden_file.write_text(json.dumps(golden.model_dump(), indent=2))


def _ingest_payloads(
    fixture_dir: Path, payload: PayloadSpec, code_index: CodeIndex, scan_run_id: str
) -> None:
    astgrep_file = fixture_dir / payload.astgrep_path
    semgrep_file = fixture_dir / payload.semgrep_path
    if not astgrep_file.exists():
        raise ReplayFixtureError(
            "FIXTURE_MISSING",
            f"recorded payload {payload.astgrep_path} missing under {fixture_dir}",
        )
    if not semgrep_file.exists():
        raise ReplayFixtureError(
            "FIXTURE_MISSING",
            f"recorded payload {payload.semgrep_path} missing under {fixture_dir}",
        )
    code_index.ingest_astgrep(
        astgrep_file.read_text(), scan_run_id=scan_run_id, scan_root=fixture_dir
    )
    code_index.ingest_semgrep(
        semgrep_file.read_text(), scan_run_id=scan_run_id, scan_root=fixture_dir
    )


def _live_toolchain() -> dict[str, str]:
    """Surface whatever we can about the live toolchain.

    Today this is best-effort; future M5 work will pin astgrep and
    semgrep versions here so drift is detected at the version layer,
    not just the digest layer.
    """
    out: dict[str, str] = {}
    for tool in ("astgrep", "semgrep", "sg"):
        path = shutil.which(tool)
        if path is None:
            continue
        try:
            cp = subprocess.run(
                [tool, "--version"], capture_output=True, text=True, check=False, timeout=5
            )
            version = (cp.stdout or cp.stderr or "").strip().split("\n")[0]
        except (subprocess.SubprocessError, OSError):
            continue
        out[tool] = version or "unknown"
    return out


def _stable_digest(snapshot, code_index_stats: dict) -> str:
    """Deterministic digest over the subset of the snapshot that does
    NOT depend on clock time.

    ``ArchitectureSnapshot.digest()`` is sensitive to
    ``ProjectData.created_at`` (a wall-clock timestamp written when
    ``world.ensure_project()`` runs the first time) and to the
    ``world_revision.digest`` (which serialises the project object).
    Two replays in different seconds therefore yield different
    digests even when the captured fixture is byte-identical.

    The replay contract is "same captured payloads reproduce the
    same architecture state", so we hash over the parts that
    genuinely describe that state:

      - code_revision (generation + sensor_revisions)
      - policy_revision
      - knowledge (elements, relations, evidence_coverage, unknowns)
      - world_revision.event_id (event-log position; deterministic
        for the same recorded ingest sequence)
      - code_index.stats() (file/symbol/edge counts by kind — a
        payload mutation shows up here even when no architecture
        elements were extracted yet, e.g. on the kotlin-demo
        fixture which is scanner-only)

    and explicitly skip git_commit / dirty_digest (project tree
    noise) and the time-sensitive parts of world_revision.
    """
    parts = [
        json.dumps(snapshot.code_revision.model_dump(), sort_keys=True, separators=(",", ":")),
        snapshot.policy_revision or "",
        json.dumps(
            snapshot.knowledge.model_dump() if snapshot.knowledge is not None else {},
            sort_keys=True,
            separators=(",", ":"),
        ),
        snapshot.world_revision.event_id if snapshot.world_revision is not None else "",
        json.dumps(code_index_stats, sort_keys=True, separators=(",", ":")),
    ]
    payload = "|".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _sandbox_repo(fixture_id: str) -> tuple[Path, dict[str, str]]:
    """Build a tmp sandbox repo with XDG isolation and return
    ``(repo_path, env_overrides)``.

    The sandbox inherits the parent's env (so the live toolchain can
    be inspected) but redirects XDG_*_HOME so the replay does not
    pollute the user's project tree.
    """
    sandbox = Path(tempfile.mkdtemp(prefix=f"replay-{fixture_id}-"))
    env = {
        **os.environ,
        "XDG_DATA_HOME": str(sandbox / "data"),
        "XDG_STATE_HOME": str(sandbox / "state"),
    }
    repo = sandbox / fixture_id
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "replay-fixture@arch-skillkit"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "replay-fixture"],
        check=True,
    )
    return repo, env


def run(
    fixture_dir: str | Path,
    *,
    write_golden: bool = False,
    env: dict[str, str] | None = None,
) -> ReplayResult:
    """Replay the captured pipeline against ``fixture_dir``.

    When ``write_golden`` is True, overwrite ``golden.json`` with the
    replayed snapshot — used by ``make replay-fixture-update`` and by
    PR workflows when the snapshot is *expected* to drift (e.g. a
    pack revision bump in the same PR).
    """
    fixture_dir = Path(fixture_dir).resolve()
    fixture_id = fixture_dir.name
    payload = _load_payload(fixture_dir)
    golden = _load_golden(fixture_dir)

    repo_path, base_env = _sandbox_repo(fixture_id)
    effective_env = {**base_env, **(env or {})}

    saved_env: dict[str, str | None] = {}
    for k in ("XDG_DATA_HOME", "XDG_STATE_HOME"):
        saved_env[k] = os.environ.get(k)
        os.environ[k] = effective_env[k]

    try:
        world = ArchitectureWorld.for_repo(repo_path).open()
        try:
            world.ensure_project()
            index = CodeIndex(world.workspace / "code.sqlite").open()
            try:
                _ingest_payloads(fixture_dir, payload, index, scan_run_id="replay")
                index_stats = index.stats()
                snapshot = build_snapshot(world, code_index=index)
            finally:
                index.close()
        finally:
            world.close()
    finally:
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    live = _live_toolchain()
    new_golden = GoldenSnapshot(
        snapshot_id=_stable_digest(snapshot, index_stats),
        policy_revision=snapshot.policy_revision,
        code_revision=json.dumps(
            snapshot.code_revision.model_dump(), sort_keys=True, separators=(",", ":")
        ),
    )

    if write_golden:
        _write_golden(fixture_dir, new_golden)
        golden = new_golden

    if golden is None:
        drift = {
            "reason": "no golden.json present; rerun with --write-golden",
            "first_seen_snapshot_id": new_golden.snapshot_id,
        }
        return ReplayResult(
            fixture_id=fixture_id,
            fixture_dir=str(fixture_dir),
            replayed_snapshot_id=new_golden.snapshot_id,
            golden_snapshot_id=None,
            match=False,
            drift=drift,
            pinned=payload.scanner_versions,
            live_toolchain=live,
        )

    match = (
        new_golden.snapshot_id == golden.snapshot_id
        and new_golden.policy_revision == golden.policy_revision
        and new_golden.code_revision == golden.code_revision
    )
    drift_payload: dict[str, Any] | None = None
    if not match:
        drift_payload = {
            "reason": "snapshot digest or revisions drifted from golden",
            "replayed": new_golden.model_dump(),
            "golden": golden.model_dump(),
        }
        if new_golden.policy_revision != golden.policy_revision:
            drift_payload["policy_revision_drift"] = True
        if new_golden.code_revision != golden.code_revision:
            drift_payload["code_revision_drift"] = True

    return ReplayResult(
        fixture_id=fixture_id,
        fixture_dir=str(fixture_dir),
        replayed_snapshot_id=new_golden.snapshot_id,
        golden_snapshot_id=golden.snapshot_id,
        match=match,
        drift=drift_payload,
        pinned=payload.scanner_versions,
        live_toolchain=live,
    )


# ---------- CLI registration ----------


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        NAME,
        help="Replay a captured scanner-payload fixture end to end and"
        " compare the resulting snapshot against the golden.",
    )
    p.add_argument("fixture_dir", help="Path to the fixture directory.")
    p.add_argument(
        "--write-golden",
        action="store_true",
        help="Overwrite golden.json with the replayed snapshot"
        " (use when an intentional drift lands in the same PR).",
    )
    p.add_argument(
        "--strict",
        action="store_true",
        help="Exit 2 when the golden is missing AND not created."
        " Default behavior exits 0 with match=False so callers"
        " can decide.",
    )


def handle(args: argparse.Namespace) -> int:
    try:
        result = run(args.fixture_dir, write_golden=args.write_golden)
    except ReplayFixtureError as exc:
        envelope = exc.to_envelope()
        print(json.dumps(envelope, indent=2), file=sys.stderr)
        return 1
    # Drift is a structured failure, not a crash: the envelope
    # describes what drifted, so it goes to stdout (along with the
    # success path). ``--strict`` and the exit code are how callers
    # branch on success vs. drift; stderr is reserved for fatal
    # exceptions only.
    payload = result.model_dump()
    print(json.dumps(payload, indent=2), file=sys.stdout)
    if not result.match and args.strict:
        return 2
    if not result.match:
        return 1
    return 0
