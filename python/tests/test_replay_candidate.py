"""Replay-candidate V2.4 M4 slice 19 (docs/v2/58 gate "replay fixture
without API key", docs/v2/56 §10).

Three angles:

  1. Record -- capture a candidate's provenance + diff + verdict into
     a fixture JSON. The fixture is the deterministic artifact CI
     replays without an LLM.

  2. Replay -- load the fixture, re-extract the live candidate's
     provenance + diff + verdict, and compare. Match means the
     candidate is what the fixture says it is (no drift in
     provenance, diff, or verdict).

  3. Drift -- tamper with the fixture's expected diff or provenance
     key and verify the replay exits 1 with the drift description
     under ``drift.*`` in the envelope.

The prompt spec registry is in-process (M5 will move it to disk);
we use the only registered spec (``architecture-analyst``) and
version the skill via ``ARCH_SKILLKIT_SKILLS_ROOT`` so the
registry picks it up.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures"

PROMPT_SPEC = "architecture-analyst"
SKILL_NAME = "replay-test-skill"


def _run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "archskillkit", *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
    )


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture()
def sandbox_repo(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    repo = tmp_path / "replay-cand"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "r@r")
    _git(repo, "config", "user.name", "r")
    _git(repo, "remote", "add", "origin", "https://github.com/rubentxu/kotlin-demo.git")
    _run("init", "--repo", str(repo), cwd=tmp_path)
    return repo


def _make_versioned_skill(tmp_path: Path) -> Path:
    """Create a skill dir with a SKILL.md carrying a version:
    frontmatter so the registry recognises it as a versioned skill."""
    skill_dir = tmp_path / "skills" / SKILL_NAME
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(f"""---
name: {SKILL_NAME}
version: "1.0.0"
description: skill used by replay-candidate tests
---
# {SKILL_NAME}

Provides test coverage for slice 19 deterministic replay.
""")
    return tmp_path / "skills"


def _ingest_kotlin(sandbox_repo: Path) -> None:
    """Populate the world with the Kotlin scanner payloads so the
    candidate fork has a non-trivial projection to diff against."""
    FIX = FIXTURE_DIR
    code_db = sandbox_repo.parent / "data" / "code.sqlite"
    from archskillkit.codeindex import CodeIndex

    db = CodeIndex(code_db)
    db.open()
    db.ingest_astgrep(
        (FIX / "astgrep-kotlin.json").read_text(), scan_run_id="replay", scan_root=FIX
    )
    db.ingest_semgrep(
        (FIX / "semgrep-kotlin.json").read_text(), scan_run_id="replay", scan_root=FIX
    )
    db.close()


def _create_candidate(
    sandbox_repo: Path, name: str, tmp_path: Path, monkeypatch
) -> subprocess.CompletedProcess:
    """Create a candidate with provenance metadata via subprocess."""
    skills_root = _make_versioned_skill(tmp_path)
    monkeypatch.setenv("ARCH_SKILLKIT_SKILLS_ROOT", str(skills_root))
    return _run(
        "proposals",
        "--repo",
        str(sandbox_repo),
        "create",
        "--name",
        name,
        "--prompt-spec",
        PROMPT_SPEC,
        "--skill",
        SKILL_NAME,
        cwd=tmp_path,
    )


# ---- Record + Replay happy path ------------------------------------------


def test_record_then_replay_roundtrip(sandbox_repo, tmp_path, monkeypatch):
    """End-to-end: init world, ingest, create a candidate with
    provenance, record a fixture, replay it, expect match."""
    _ingest_kotlin(sandbox_repo)
    cp = _create_candidate(sandbox_repo, "alpha", tmp_path, monkeypatch)
    assert cp.returncode == 0, cp.stdout + cp.stderr

    fixture = tmp_path / "alpha.fixture.json"
    cp_record = _run(
        "replay-candidate",
        "alpha",
        "--fixture",
        str(fixture),
        "--record",
        "--repo",
        str(sandbox_repo),
    )
    assert cp_record.returncode == 0, cp_record.stdout + cp_record.stderr
    assert fixture.exists()

    cp_replay = _run(
        "replay-candidate", "alpha", "--fixture", str(fixture), "--repo", str(sandbox_repo)
    )
    assert cp_replay.returncode == 0, cp_replay.stdout + cp_replay.stderr
    payload = json.loads(cp_replay.stdout)
    assert payload["schema"] == "arch-skillkit/candidate-replay-result-v1"
    assert payload["match"] is True
    assert payload["provenance_match"] is True
    assert payload["diff_match"] is True
    assert payload["verdict_match"] is True
    assert payload["drift"] is None


# ---- Drift detection -----------------------------------------------------


def test_drift_when_diff_tampered(sandbox_repo, tmp_path, monkeypatch):
    """When the fixture's structural_diff is rewritten to lie about
    the candidate, the replay must surface the mismatch under
    ``drift.structural_diff.field_drift`` and exit 1."""
    _ingest_kotlin(sandbox_repo)
    cp = _create_candidate(sandbox_repo, "beta", tmp_path, monkeypatch)
    assert cp.returncode == 0, cp.stdout + cp.stderr

    fixture = tmp_path / "beta.fixture.json"
    _run(
        "replay-candidate",
        "beta",
        "--fixture",
        str(fixture),
        "--record",
        "--repo",
        str(sandbox_repo),
    )

    raw = json.loads(fixture.read_text())
    raw["outcome"]["structural_diff"]["is_empty"] = not raw["outcome"]["structural_diff"].get(
        "is_empty", True
    )
    fixture.write_text(json.dumps(raw, indent=2))

    cp_replay = _run(
        "replay-candidate", "beta", "--fixture", str(fixture), "--repo", str(sandbox_repo)
    )
    assert cp_replay.returncode == 1
    payload = json.loads(cp_replay.stdout)
    assert payload["match"] is False
    assert payload["diff_match"] is False
    assert "structural_diff" in payload["drift"]


def test_drift_when_provenance_tampered(sandbox_repo, tmp_path, monkeypatch):
    """When the fixture's prompt_spec_hash is rewritten, the replay
    must surface the provenance drift and exit 1."""
    _ingest_kotlin(sandbox_repo)
    cp = _create_candidate(sandbox_repo, "gamma", tmp_path, monkeypatch)
    assert cp.returncode == 0, cp.stdout + cp.stderr

    fixture = tmp_path / "gamma.fixture.json"
    _run(
        "replay-candidate",
        "gamma",
        "--fixture",
        str(fixture),
        "--record",
        "--repo",
        str(sandbox_repo),
    )

    raw = json.loads(fixture.read_text())
    raw["provenance"]["prompt_spec_hash"] = "a" * 64
    fixture.write_text(json.dumps(raw, indent=2))

    cp_replay = _run(
        "replay-candidate", "gamma", "--fixture", str(fixture), "--repo", str(sandbox_repo)
    )
    assert cp_replay.returncode == 1
    payload = json.loads(cp_replay.stdout)
    assert payload["provenance_match"] is False
    assert "provenance" in payload["drift"]


def test_replay_candidate_not_found(sandbox_repo, tmp_path):
    """Replay against a name that doesn't exist surfaces a stable
    CANDIDATE_NOT_FOUND code, not a stack trace."""
    fixture = tmp_path / "nonexistent.fixture.json"
    # The fixture file must exist so ``_load_fixture`` parses it;
    # the candidate-not-found check happens after parsing.
    fixture.write_text(
        json.dumps(
            {
                "schema": "arch-skillkit/candidate-replay-fixture-v1",
                "candidate_name": "missing",
                "provenance": {"prompt_spec_hash": "x" * 64, "skill_content_hashes": {}},
                "outcome": {"structural_diff": {}, "review_pass": False, "gate_verdict": "unknown"},
            },
            indent=2,
        )
    )
    cp = _run("replay-candidate", "missing", "--fixture", str(fixture), "--repo", str(sandbox_repo))
    assert cp.returncode == 1
    payload = json.loads(cp.stderr)
    assert payload["error"] == "CANDIDATE_NOT_FOUND"


def test_replay_schema_mismatch(sandbox_repo, tmp_path):
    """A fixture whose schema field is wrong is rejected with
    FIXTURE_SCHEMA_INVALID — pydantic extra=forbid makes the
    rejection deterministic, not a silent drift."""
    fixture = tmp_path / "wrong.fixture.json"
    fixture.write_text(
        json.dumps(
            {
                "schema": "arch-skillkit/wrong-fixture-v9",
                "candidate_name": "x",
                "provenance": {"prompt_spec_hash": "abc", "skill_content_hashes": {}},
                "outcome": {"structural_diff": {}, "review_pass": False, "gate_verdict": "unknown"},
            },
            indent=2,
        )
    )
    cp = _run("replay-candidate", "x", "--fixture", str(fixture), "--repo", str(sandbox_repo))
    assert cp.returncode == 1
    payload = json.loads(cp.stderr)
    assert payload["error"] == "FIXTURE_SCHEMA_INVALID"
