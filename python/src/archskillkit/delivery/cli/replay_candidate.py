"""`archskillkit replay-candidate` — verify a recorded candidate
fixture against the live candidate (V2.4 M4 slice 19, docs/v2/58
gate "replay fixture without API key", docs/v2/56 §10 "replay debe
detectar divergencia si cambia prompt hash/schema/policy").

A candidate fixture is a JSON document that records, for one
candidate run, the provenance key the LLM declared (PromptSpec
digest + per-skill content hashes) and the outcome the LLM
produced (structural diff + gate verdict). Replay loads the
fixture, opens the candidate run, and verifies that the
candidate's actual provenance + diff + verdict match the
fixture bit-for-bit. CI without an API key.

This is the deterministic verification half. The recording half
(``--record``) captures the candidate's current state into a
fresh fixture; it does NOT call an LLM driver yet — the LLM
integration lands with M5. Recording today snapshots the
candidate's current diff and verdict so the next replay can
verify them.

The fixture schema ``arch-skillkit/candidate-replay-fixture-v1``
is the contract for both halves; it is intentionally
``extra="forbid"`` so future schema bumps become a hard
``FIXTURE_SCHEMA_INVALID`` rather than a silent drift.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from archskillkit.agent_governance import get_proposal_metadata
from archskillkit.application.commands.governance import GovernanceApplicationService
from archskillkit.application.models.governance import (
    CommandError,
    ProposalDiffCommand,
    ProposalReviewCommand,
)
from archskillkit.world import ArchitectureWorld

NAME = "replay-candidate"
NEEDS_WORLD = True

SCHEMA_FIXTURE = "arch-skillkit/candidate-replay-fixture-v1"
SCHEMA_RESULT = "arch-skillkit/candidate-replay-result-v1"


class CandidateReplayError(Exception):
    """Base error for replay-candidate (V2.4 M4 slice 19)."""

    code: str = "REPLAY_FAILED"

    def __init__(self, code: str, message: str, *, candidate: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.candidate = candidate

    def to_envelope(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "schema": SCHEMA_RESULT,
            "error": self.code,
            "message": self.message,
        }
        if self.candidate is not None:
            out["candidate"] = self.candidate
        return out


class ProvenanceKey(BaseModel):
    """The provenance fingerprint the LLM declared when it produced
    the candidate (V2.4 M4 slice 16)."""

    model_config = ConfigDict(extra="forbid")

    schema: str = Field(default="arch-skillkit/provenance-key-v1")
    prompt_spec_hash: str
    skill_content_hashes: dict[str, str] = Field(default_factory=dict)


class CandidateOutcome(BaseModel):
    """The deterministic, verifiable outcome of a candidate run."""

    model_config = ConfigDict(extra="forbid")

    structural_diff: dict[str, Any]
    review_pass: bool
    gate_verdict: Literal["pass", "fail", "waived", "unknown"]


class CandidateFixture(BaseModel):
    """A recorded candidate outcome (V2.4 M4 slice 19)."""

    model_config = ConfigDict(extra="forbid")

    schema: str = Field(default=SCHEMA_FIXTURE)
    candidate_name: str
    provenance: ProvenanceKey
    outcome: CandidateOutcome


class CandidateReplayResult(BaseModel):
    """Replay verdict envelope (V2.4 M4 slice 19)."""

    model_config = ConfigDict(extra="forbid")

    schema: str = Field(default=SCHEMA_RESULT)
    candidate: str
    match: bool
    provenance_match: bool
    diff_match: bool
    verdict_match: bool
    live: CandidateOutcome
    fixture: CandidateOutcome
    drift: dict[str, Any] | None = None


def _load_fixture(path: Path) -> CandidateFixture:
    if not path.exists():
        raise CandidateReplayError(
            "FIXTURE_MISSING",
            f"fixture file not found: {path}",
        )
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise CandidateReplayError(
            "FIXTURE_MALFORMED",
            f"fixture is not valid JSON: {exc}",
        ) from exc
    if raw.get("schema") != SCHEMA_FIXTURE:
        raise CandidateReplayError(
            "FIXTURE_SCHEMA_INVALID",
            f"fixture schema is {raw.get('schema')!r}, expected {SCHEMA_FIXTURE!r}",
        )
    return CandidateFixture.model_validate(raw)


def _candidate_diff_and_verdict(
    world: ArchitectureWorld, candidate_name: str
) -> tuple[dict, bool, str]:
    """Return ``(diff_dict, review_pass, gate_verdict)`` for the
    named candidate. Direct call to GovernanceApplicationService;
    no cross-CLI round-trip or stdout capture.
    """
    service = GovernanceApplicationService(world)

    diff_cmd = ProposalDiffCommand(name=candidate_name)
    diff_result = service.diff_proposal(diff_cmd)
    if isinstance(diff_result, CommandError):
        raise CandidateReplayError(
            "DIFF_FAILED",
            f"diff_proposal returned {diff_result.error}: {diff_result.message}",
            candidate=candidate_name,
        )
    diff_dict = diff_result.structural_diff

    review_cmd = ProposalReviewCommand(
        name=candidate_name,
        min_coverage=0.8,
        max_unknowns=0,
        max_findings=0,
        max_run_age_days=30,
        require_pass=False,
    )
    review_result = service.review_proposal(review_cmd, index=None)
    if isinstance(review_result, CommandError):
        passed = False
        verdict = "unknown"
    else:
        gate = review_result.gate or {}
        verdict = gate.get("verdict") or "unknown"
        passed = verdict == "pass"
    return diff_dict, passed, verdict


def _candidate_provenance(world: ArchitectureWorld, candidate_name: str) -> ProvenanceKey:
    """Read the provenance metadata recorded for the candidate
    (V2.4 M4 slice 16). Returns ``ProvenanceKey`` keyed on
    ``prompt_spec_hash`` + per-skill ``content_hash``."""
    run_id, err = _resolve_run_id(world, candidate_name)
    if err is not None:
        raise CandidateReplayError(
            "CANDIDATE_NOT_FOUND",
            f"candidate {candidate_name!r} not found: {err['message']}"
            if isinstance(err, dict)
            else str(err),
            candidate=candidate_name,
        )
    metadata = get_proposal_metadata(world, run_id)
    if metadata is None:
        raise CandidateReplayError(
            "PROVENANCE_MISSING",
            f"candidate {candidate_name!r} carries no provenance"
            f" metadata (was it created with --prompt-spec and"
            f" --skill, slice 16?).",
            candidate=candidate_name,
        )
    skill_hashes = {s.name: s.content_hash for s in metadata.skill_revisions}
    return ProvenanceKey(
        prompt_spec_hash=metadata.prompt_spec_hash,
        skill_content_hashes=skill_hashes,
    )


def _resolve_run_id(
    world: ArchitectureWorld, name: str
) -> tuple[str | None, dict[str, Any] | None]:
    """Mirror ``_require_candidate`` from proposals.py without the
    stdout prints. Returns ``(run_id, error_envelope)`` — exactly
    one is non-None."""
    run_id = f"proposal-{name}"
    if not world.has_run(run_id):
        return None, {
            "error": "CANDIDATE_NOT_FOUND",
            "message": f"no candidate '{name}' (run: archskillkit proposals create --name {name})",
            "name": name,
            "run_id": run_id,
        }
    return run_id, None


def _diff_keys_differs(expected: dict, actual: dict) -> dict[str, Any]:
    """Return a structured drift description when two diff dicts
    differ. Field-level: each key whose value differs is reported
    under ``field_drift``."""
    field_drift: dict[str, Any] = {}
    keys = set(expected) | set(actual)
    for k in keys:
        if expected.get(k) != actual.get(k):
            field_drift[k] = {"expected": expected.get(k), "actual": actual.get(k)}
    return {"field_drift": field_drift} if field_drift else {}


def run(
    world: ArchitectureWorld,
    candidate_name: str,
    *,
    fixture_path: Path,
) -> CandidateReplayResult:
    """Verify the named candidate matches the recorded fixture."""
    fixture = _load_fixture(fixture_path)
    if fixture.candidate_name != candidate_name:
        raise CandidateReplayError(
            "FIXTURE_CANDIDATE_MISMATCH",
            f"fixture is for candidate {fixture.candidate_name!r},"
            f" but replay was asked about {candidate_name!r}",
            candidate=candidate_name,
        )
    live_provenance = _candidate_provenance(world, candidate_name)
    live_diff, live_pass, live_verdict = _candidate_diff_and_verdict(world, candidate_name)

    provenance_match = (
        live_provenance.prompt_spec_hash == fixture.provenance.prompt_spec_hash
        and live_provenance.skill_content_hashes == fixture.provenance.skill_content_hashes
    )
    diff_match = live_diff == fixture.outcome.structural_diff
    verdict_match = (
        live_pass == fixture.outcome.review_pass and live_verdict == fixture.outcome.gate_verdict
    )

    live_outcome = CandidateOutcome(
        structural_diff=live_diff,
        review_pass=live_pass,
        gate_verdict=live_verdict,  # type: ignore[arg-type]
    )
    match = provenance_match and diff_match and verdict_match
    drift: dict[str, Any] | None = None
    if not match:
        drift = {}
        if not provenance_match:
            drift["provenance"] = {
                "live": live_provenance.model_dump(),
                "fixture": fixture.provenance.model_dump(),
            }
        if not diff_match:
            drift["structural_diff"] = _diff_keys_differs(
                fixture.outcome.structural_diff, live_diff
            )
        if not verdict_match:
            drift["verdict"] = {
                "live": {"review_pass": live_pass, "gate_verdict": live_verdict},
                "fixture": {
                    "review_pass": fixture.outcome.review_pass,
                    "gate_verdict": fixture.outcome.gate_verdict,
                },
            }
    return CandidateReplayResult(
        candidate=candidate_name,
        match=match,
        provenance_match=provenance_match,
        diff_match=diff_match,
        verdict_match=verdict_match,
        live=live_outcome,
        fixture=fixture.outcome,
        drift=drift,
    )


def record(world: ArchitectureWorld, candidate_name: str, output_path: Path) -> CandidateFixture:
    """Capture the candidate's current state into a fresh fixture.

    Today this snapshots provenance + diff + verdict. When the LLM
    driver lands (M5) the recorder will additionally capture the
    tool_call sequence the driver produced so the replay can
    reproduce it byte-for-byte.
    """
    provenance = _candidate_provenance(world, candidate_name)
    diff, passed, verdict = _candidate_diff_and_verdict(world, candidate_name)
    outcome = CandidateOutcome(
        structural_diff=diff,
        review_pass=passed,
        gate_verdict=verdict,  # type: ignore[arg-type]
    )
    fixture = CandidateFixture(
        candidate_name=candidate_name,
        provenance=provenance,
        outcome=outcome,
    )
    output_path.write_text(json.dumps(fixture.model_dump(), indent=2))
    return fixture


# ---------- CLI registration ----------


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        NAME,
        help="Verify a recorded candidate fixture against the live"
        " candidate. No API key needed; this is the deterministic"
        " half of LLM replay (docs/v2/56 §10, M4 slice 19).",
    )
    p.add_argument("--repo", required=True)
    p.add_argument("candidate", help="Candidate name.")
    p.add_argument(
        "--fixture",
        required=True,
        help="Path to the recorded candidate fixture JSON.",
    )
    p.add_argument(
        "--record",
        action="store_true",
        help="Capture the candidate's current state into a fresh"
        " fixture at --fixture and exit. The LLM driver"
        " integration (M5) will extend this to record the"
        " tool_call sequence too.",
    )


def handle(args: argparse.Namespace, world: ArchitectureWorld) -> int:
    fixture_path = Path(args.fixture).resolve()
    try:
        if args.record:
            fixture = record(world, args.candidate, fixture_path)
            print(json.dumps(fixture.model_dump(), indent=2))
            return 0
        result = run(world, args.candidate, fixture_path=fixture_path)
    except CandidateReplayError as exc:
        envelope = exc.to_envelope()
        print(json.dumps(envelope, indent=2), file=sys.stderr)
        return 1
    payload = result.model_dump()
    print(json.dumps(payload, indent=2))
    if not result.match:
        return 1
    return 0
