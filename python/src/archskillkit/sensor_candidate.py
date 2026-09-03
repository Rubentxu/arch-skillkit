"""SensorCandidate schema + deterministic precision/recall harness (V2.4 M6 slice 28).

Schema version: arch-skillkit/sensor-candidate-v1
Evaluation schema: arch-skillkit/sensor-eval-v1

The Sensor Distiller (docs/v2/53 §Sensor Distiller) detects repeated LLM
inferences and proposes deterministic sensor rules with positive/negative
fixture sets.  Promotion to an active sensor requires the harness to prove
precision ≥ threshold AND recall ≥ threshold against the fixture corpus — it
never auto-promotes (docs/v2/53 §Sensor Distiller: "requiere tests/UAT
antes de promoción").

origin_run_ids follow the RunLedger contract (run_ledger.py): each entry is
a run_id reference to the discovery session that contributed evidence.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ----------------------------------------------------------------------
# Schema constants
# ----------------------------------------------------------------------
CANDIDATE_SCHEMA = "arch-skillkit/sensor-candidate-v1"
EVAL_SCHEMA = "arch-skillkit/sensor-eval-v1"

SENSOR_ID_RE = r"^[a-z0-9-]{3,64}$"
FIXTURE_EXPECTS = ("match", "no-match")


# ----------------------------------------------------------------------
# SensorCandidate model
# ----------------------------------------------------------------------
class DetectorRule(BaseModel):
    """Inline rule source for the detector engine."""

    model_config = ConfigDict(extra="forbid")

    engine: Literal["ast-grep", "semgrep"]
    rule: str  # raw rule source text (ast-grep YAML or Semgrep JSON)


class SensorCandidate(BaseModel):
    """A proposed deterministic sensor rule with a labelled fixture corpus.

    Produced by the Sensor Distiller (docs/v2/53); evaluated by
    ``evaluate_sensor`` before promotion.
    """

    model_config = ConfigDict(extra="forbid")

    schema: Literal["arch-skillkit/sensor-candidate-v1"] = CANDIDATE_SCHEMA  # type: ignore[assignment]

    sensor_id: str
    title: str
    detector: DetectorRule
    language: str  # e.g. "python", "typescript" — used to select engine parser
    positives: list[dict] = Field(min_length=1)
    negatives: list[dict] = Field(min_length=1)
    origin_run_ids: list[str] = Field(min_length=1)
    status: Literal["candidate", "accepted", "rejected"] = "candidate"
    created_at: str
    metrics: dict = Field(default_factory=dict)

    @field_validator("sensor_id")
    @classmethod
    def _check_sensor_id(cls, v: str) -> str:
        if not re.match(SENSOR_ID_RE, v):
            raise ValueError(f"sensor_id must match {SENSOR_ID_RE!r}, got {v!r}")
        return v

    @field_validator("positives", "negatives")
    @classmethod
    def _check_fixture(cls, v: list[dict]) -> list[dict]:
        for item in v:
            if "file" not in item or "expect" not in item:
                raise ValueError(f"each fixture must have 'file' and 'expect', got {item!r}")
            if item["expect"] not in FIXTURE_EXPECTS:
                raise ValueError(f"expect must be one of {FIXTURE_EXPECTS}, got {item['expect']!r}")
        return v

    @model_validator(mode="after")
    def _deterministic_order(self) -> SensorCandidate:
        """Impose deterministic fixture ordering so same candidate → byte-identical JSON."""
        self.positives = sorted(self.positives, key=lambda d: d["file"])
        self.negatives = sorted(self.negatives, key=lambda d: d["file"])
        return self

    def canonical_json(self) -> str:
        return json.dumps(self.model_dump(), sort_keys=True, separators=(",", ":"))


# ----------------------------------------------------------------------
# SensorEvaluation model
# ----------------------------------------------------------------------
class SensorEvaluation(BaseModel):
    """Result of running a detector against its fixture corpus."""

    model_config = ConfigDict(extra="forbid")

    schema: Literal["arch-skillkit/sensor-eval-v1"] = EVAL_SCHEMA  # type: ignore[assignment]

    sensor_id: str
    evaluated: bool = False
    precision: float = 0.0
    recall: float = 0.0
    reason_code: str | None = None  # e.g. "ENGINE_MISSING"
    detail: str | None = None  # human-readable supplemental info

    def canonical_json(self) -> str:
        return json.dumps(self.model_dump(), sort_keys=True, separators=(",", ":"))


# ----------------------------------------------------------------------
# Threshold check helper
# ----------------------------------------------------------------------
def meets_threshold(
    eval_result: SensorEvaluation,
    *,
    min_precision: float = 0.9,
    min_recall: float = 0.9,
) -> bool:
    """Return True when evaluated AND both metrics meet their thresholds."""
    if not eval_result.evaluated:
        return False
    return eval_result.precision >= min_precision and eval_result.recall >= min_recall


# ----------------------------------------------------------------------
# Engine availability helpers
# ----------------------------------------------------------------------
def engine_path(engine: Literal["ast-grep", "semgrep"]) -> str | None:
    """Return the executable path for the engine, or None if not on PATH or non-functional.

    Uses shutil.which() for lookup, then a minimal invocation check to
    distinguish ast-grep (sg) from a non-ast-grep binary at the same path
    (e.g. the system `newgrp` utility that shadows `sg` on some systems).
    """
    name = "sg" if engine == "ast-grep" else "semgrep"
    found = shutil.which(name)
    if found is None:
        return None
    # Distinguish real ast-grep from a shadowing binary by invoking it.
    # ast-grep exits 0 on --help; newgrp exits 1.
    try:
        result = subprocess.run(
            [found, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        # ast-grep prints something like "ast-grep version 0.x.x"
        if engine == "ast-grep" and "ast-grep" not in result.stdout:
            return None
    except (OSError, subprocess.TimeoutExpired):
        pass
    return found


# ----------------------------------------------------------------------
# Core harness
# ----------------------------------------------------------------------
def evaluate_sensor(candidate_dir: Path) -> SensorEvaluation:
    """Run the detector rule against the fixture files in ``candidate_dir``.

    ``candidate_dir`` layout::

        candidate.json       # SensorCandidate serialised JSON
        positives/           # files named in positives[].file
        negatives/           # files named in negatives[].file

    All I/O is confined to ``candidate_dir`` and a private temporary directory.
    Returns ``SensorEvaluation`` with ``evaluated=False`` and ``reason_code``
    when an engine binary is missing — NOT an exception.
    """
    candidate_path = candidate_dir / "candidate.json"
    if not candidate_path.exists():
        return SensorEvaluation(
            sensor_id="<unknown>",
            evaluated=False,
            reason_code="CANDIDATE_FILE_MISSING",
            detail=f"{candidate_path} does not exist",
        )

    try:
        raw = candidate_path.read_text()
        candidate = SensorCandidate.model_validate_json(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        return SensorEvaluation(
            sensor_id=getattr(candidate_path, "stem", "<unknown>"),
            evaluated=False,
            reason_code="CANDIDATE_PARSE_ERROR",
            detail=str(exc),
        )

    eng = candidate.detector.engine
    eng_bin = engine_path(eng)
    if eng_bin is None:
        return SensorEvaluation(
            sensor_id=candidate.sensor_id,
            evaluated=False,
            reason_code="ENGINE_MISSING",
            detail=f"{eng} is not on PATH",
        )

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # Write the inline rule
        if eng == "ast-grep":
            rule_file = tmp / "rule.yaml"
        else:
            rule_file = tmp / "rule.json"
        rule_file.write_text(candidate.detector.rule)

        # Copy fixture files into the temp scan dir (positives/ and negatives/)
        # so the engine scans them; preserve directory structure engine expects
        pos_tmp = tmp / "positives"
        neg_tmp = tmp / "negatives"
        pos_tmp.mkdir()
        neg_tmp.mkdir()

        for fixture in candidate.positives:
            src = candidate_dir / "positives" / fixture["file"]
            if src.exists():
                shutil.copy2(src, pos_tmp / fixture["file"])

        for fixture in candidate.negatives:
            src = candidate_dir / "negatives" / fixture["file"]
            if src.exists():
                shutil.copy2(src, neg_tmp / fixture["file"])

        # Execute the engine
        try:
            raw_output = _run_engine(eng, eng_bin, rule_file, tmp)
        except subprocess.TimeoutExpired:
            return SensorEvaluation(
                sensor_id=candidate.sensor_id,
                evaluated=False,
                reason_code="ENGINE_TIMEOUT",
                detail="engine execution exceeded 120 s timeout",
            )
        except OSError as exc:
            return SensorEvaluation(
                sensor_id=candidate.sensor_id,
                evaluated=False,
                reason_code="ENGINE_ERROR",
                detail=str(exc),
            )

        # Extract matching filenames
        try:
            detected: set[str] = _parse_output(raw_output, eng)
        except (json.JSONDecodeError, ValueError, KeyError) as exc:
            return SensorEvaluation(
                sensor_id=candidate.sensor_id,
                evaluated=False,
                reason_code="OUTPUT_PARSE_ERROR",
                detail=str(exc),
            )

        # Compute precision / recall
        tp = fp = fn = 0

        for fixture in candidate.positives:
            fname = fixture["file"]
            if fname in detected:
                tp += 1
            else:
                fn += 1

        for fixture in candidate.negatives:
            fname = fixture["file"]
            if fname in detected:
                fp += 1
            # tn: no contribution

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0

        return SensorEvaluation(
            sensor_id=candidate.sensor_id,
            evaluated=True,
            precision=precision,
            recall=recall,
            detail=(
                f"tp={tp} fp={fp} fn={fn}; "
                f"positives={len(candidate.positives)} "
                f"negatives={len(candidate.negatives)}"
            ),
        )


# ----------------------------------------------------------------------
# Internal helpers (pure, deterministic)
# ----------------------------------------------------------------------
def _run_engine(
    engine: Literal["ast-grep", "semgrep"],
    binary_path: str,
    rule_file: Path,
    scan_dir: Path,
) -> str:
    """Execute the engine; return combined stdout+stderr text."""
    if engine == "ast-grep":
        # ast-grep CLI: sg scan --json --config <rule_file> <dir> ...
        cmd = [
            binary_path,
            "scan",
            "--json",
            "--config",
            str(rule_file),
            str(scan_dir / "positives"),
            str(scan_dir / "negatives"),
        ]
    else:
        # Semgrep CLI: semgrep --json --config <rule_file> <dir>
        cmd = [
            binary_path,
            "--json",
            "--config",
            str(rule_file),
            str(scan_dir),
        ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    return result.stdout + result.stderr


def _parse_output(
    raw_output: str,
    engine: Literal["ast-grep", "semgrep"],
) -> set[str]:
    """Extract set of relative file paths that matched from engine JSON output.

    Handles both a single JSON document and NDJSON (one JSON object per line).
    """
    if not raw_output.strip():
        return set()

    matched: set[str] = set()

    # Try whole-document parse first
    try:
        data = json.loads(raw_output)
        _ingest_matches(matched, data, engine)
        return matched
    except json.JSONDecodeError:
        pass

    # NDJSON fallback
    for line in raw_output.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            _ingest_matches(matched, obj, engine)
        except json.JSONDecodeError:
            continue

    return matched


def _ingest_matches(
    matched: set[str],
    data: dict | list,
    engine: Literal["ast-grep", "semgrep"],
) -> None:
    """Recursively collect matching file paths from parsed JSON."""
    if isinstance(data, list):
        for item in data:
            _ingest_matches(matched, item, engine)
    elif isinstance(data, dict):
        if engine == "ast-grep":
            # ast-grep match record: {"file": "...", ...}
            if "file" in data and isinstance(data["file"], str):
                matched.add(data["file"])
        else:
            # Semgrep result record: {"path": "...", ...}
            if "path" in data and isinstance(data["path"], str):
                matched.add(data["path"])
        for value in data.values():
            _ingest_matches(matched, value, engine)
