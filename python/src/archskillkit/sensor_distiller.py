"""Sensor Distiller — detect repeated LLM inferences and propose SensorCandidates.

V2.4 M6 slice 29.  Pure module: no I/O beyond the passed world, never
mutates the world.

Signature grouping strategy
==========================
ClaimData (packs/arch_core.py §ClaimData) has these fields relevant to
INFERRED-origin claims::

    origin: Literal["DETECTED", "INFERRED", "DECLARED", "OBSERVED"]
    statement: str       # what the LLM inferred
    subjects: list[str]  # architectural elements involved
    relations: list[str]
    evidence_refs: list[str]
    status: ClaimStatus

There is no ``rule`` or ``kind`` field in ClaimData.  The closest
deterministic equivalent for a repeated-inference signature is therefore the
pair ``(sorted(subjects), statement)``.  This is stable across runs because
both fields are stored verbatim in the graph event log.  We also accept a
normalised form of ``statement`` (stripped, lowercased) to make the grouping
insensitive to minor formatting differences between LLM invocations.

AST-grep rule derivation
========================
Because ClaimData carries no concrete code-pattern field, the detector rule
is a best-effort heuristic: we emit a minimal ast-grep YAML whose
``pattern`` matches the claim ``statement`` as a string-literal token.  This
has known limitations (it will not match variable names or跨文件 references)
and is documented as a proposal that requires human review before promotion.

CLI
===
``archskillkit distill-sensors --repo PATH [--min-runs N]``

Schema: arch-skillkit/sensor-distillation-v1
"""

from __future__ import annotations

import datetime as _dt
import re
import textwrap
from collections import defaultdict
from typing import TYPE_CHECKING

from archskillkit.sensor_candidate import DetectorRule, SensorCandidate

if TYPE_CHECKING:
    from archskillkit.world import ArchitectureWorld

# ----------------------------------------------------------------------
# Signature derivation
# ----------------------------------------------------------------------


def _normalise(text: str) -> str:
    """Strip and lowercase for signature comparison."""
    return " ".join(text.strip().lower().split())


def _derive_signature(claim_data: dict) -> tuple[tuple[str, ...], str]:
    """Return grouping key for an INFERRED claim.

    Returns ((sorted subjects), normalised statement).
    Evidence: packs/arch_core.py:57-68 (ClaimData fields).
    """
    subjects = tuple(sorted(claim_data.get("subjects", [])))
    statement = _normalise(claim_data.get("statement", ""))
    return (subjects, statement)


def _make_sensor_id(signature: tuple[tuple[str, ...], str]) -> str:
    """Derive a deterministic sensor_id from the grouping signature.

    Format: inferred-<slugified-statement>[-<first-subject>]...
    The statement slug is capped at 40 chars to keep sensor_id within the
    64-char limit (SENSOR_ID_RE = ^[a-z0-9-]{3,64}$).
    """
    subjects, statement = signature
    # Slugify the statement
    slug = re.sub(r"[^a-z0-9]+", "-", statement.strip().lower())
    slug = re.sub(r"-+", "-", slug).strip("-")
    if len(slug) > 40:
        slug = slug[:40].rstrip("-")
    parts = [f"inferred-{slug}"] if slug else ["inferred"]
    # Append up to 2 subjects for disambiguation
    for s in subjects[:2]:
        part = re.sub(r"[^a-z0-9]+", "-", s.lower())
        part = re.sub(r"-+", "-", part).strip("-")
        if part and len(part) <= 20:
            parts.append(part)
    return "-".join(parts)[:64]


def _build_astgrep_rule(statement: str, subjects: list[str]) -> str:
    """Build a minimal ast-grep YAML rule from the claim statement.

    The rule uses a string pattern with context ``$STATEMENT`` to match
    occurrences of the inferred text in the codebase.  This is a
    best-effort heuristic; see module docstring limitations.
    """
    # Escape for YAML single-quoted string
    escaped = statement.replace("\\", "\\\\").replace("'", "\\'")
    subject_part = ", ".join(f"'{s}'" for s in subjects[:3]) if subjects else ""
    rule_id = re.sub(r"[^a-z0-9]+", "-", statement.strip().lower())[:30]

    return textwrap.dedent(f"""\
        id: {rule_id}
        language: Python
        message: |
          Inferred architecture claim: {escaped}
          Subjects: {subject_part}
        severity: info
        pattern: $STATEMENT
        fix: |
          # Review required: this pattern was inferred from repeated
          # LLM inferences and must be validated before promotion.
        options:
          timeout: 30
        """)


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------


def distill(
    world: ArchitectureWorld,
    *,
    min_runs: int = 2,
    min_occurrences: int = 2,
) -> list[SensorCandidate]:
    """Detect repeated LLM inferences and propose SensorCandidates.

    Scans every run in the world (main + forks via ``world.list_runs()`` /
    ``world.view``) for claims whose ``data.origin == "INFERRED"``.

    Groups INFERRED claims by the deterministic signature
    ``(sorted(subjects), normalised statement)``.  A signature that appears
    in ``>= min_runs`` distinct runs with ``>= min_occurrences`` total
    claims becomes a ``SensorCandidate`` with:

    - ``sensor_id`` derived from the signature (slugified, deterministic)
    - ``detector`` = ``{"engine": "ast-grep", "rule": <proposed YAML>}``
    - ``origin_run_ids`` = sorted list of run ids where it appeared
    - ``positives`` / ``negatives`` = ``[]``  (human curators add fixtures)
    - ``status`` = ``"candidate"``  (never auto-promoted)
    - ``metrics`` = ``{"evaluated": False}``

    The function is pure: it reads from the world but never mutates it.

    Parameters
    ----------
    world
        An open ``ArchitectureWorld`` instance.
    min_runs
        Minimum distinct runs a signature must appear in (default 2).
    min_occurrences
        Minimum total claims across all runs (default 2).

    Returns
    -------
    list[SensorCandidate]
        Candidates sorted by ``sensor_id`` (lexicographic, deterministic).
    """
    if min_runs < 1 or min_occurrences < 1:
        raise ValueError(
            f"min_runs and min_occurrences must be >= 1, got {min_runs}, {min_occurrences}"
        )

    run_ids = world.list_runs()

    # Collect (signature -> {run_id -> [claim_data]})
    sig_to_runs: dict[
        tuple[tuple[str, ...], str],
        dict[str, list[dict]],
    ] = defaultdict(lambda: defaultdict(list))

    for run_id in run_ids:
        if run_id == world.run_id:
            # Main world is already open; scan directly
            claim_objs = world.find_objects("claim")
        else:
            # Fork run — use claims_by_run to avoid fork-view inheritance
            # (fork runtimes show parent events too; we need only this run's)
            claim_objs = world.claims_by_run(run_id)

        for obj in claim_objs:
            data = obj.get("data", {})
            if data.get("origin") != "INFERRED":
                continue
            sig = _derive_signature(data)
            sig_to_runs[sig][run_id].append(data)

    candidates: list[SensorCandidate] = []
    created_at = _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    for sig, run_map in sig_to_runs.items():
        total_occurrences = sum(len(claims) for claims in run_map.values())
        distinct_runs = len(run_map)

        if distinct_runs < min_runs or total_occurrences < min_occurrences:
            continue

        subjects, statement = sig
        sensor_id = _make_sensor_id(sig)
        ast_rule = _build_astgrep_rule(statement, list(subjects))
        origin_run_ids = sorted(run_map.keys())

        candidates.append(
            SensorCandidate(
                sensor_id=sensor_id,
                title=f"Inferred: {statement[:80]}",
                detector=DetectorRule(engine="ast-grep", rule=ast_rule),
                language="python",  # default; human reviewer refines per case
                positives=[],
                negatives=[],
                origin_run_ids=origin_run_ids,
                status="candidate",
                created_at=created_at,
                metrics={"evaluated": False},
            )
        )

    candidates.sort(key=lambda c: c.sensor_id)
    return candidates
