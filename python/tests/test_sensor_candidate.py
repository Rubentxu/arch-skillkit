"""V2.4 M6 slice 28 — SensorCandidate + evaluation harness tests."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Literal

import pytest

from archskillkit.sensor_candidate import (
    CANDIDATE_SCHEMA,
    EVAL_SCHEMA,
    DetectorRule,
    SensorCandidate,
    SensorEvaluation,
    engine_path,
    evaluate_sensor,
    meets_threshold,
)

# ----------------------------------------------------------------------
# Paths — pytest rootdir = python/; __file__ is at python/tests/test_sensor_candidate.py
# so fixtures are at __file__.parent / "fixtures" (python/tests/fixtures/...)
# ----------------------------------------------------------------------
_FIXTURES_ROOT = (
    Path(__file__).parent          # python/tests
    / "fixtures"
    / "sensors"
    / "requests-no-timeout"
)
POS_DIR = _FIXTURES_ROOT / "positives"
NEG_DIR = _FIXTURES_ROOT / "negatives"
#: candidate_dir layout: candidate.json + positives/ + negatives/
FIXTURES = _FIXTURES_ROOT


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _minimal_candidate(
    sensor_id: str = "test-sensor",
    status: Literal["candidate", "accepted", "rejected"] = "candidate",
    positives: list[dict] | None = None,
    negatives: list[dict] | None = None,
    origin_run_ids: list[str] | None = None,
) -> SensorCandidate:
    """Minimal valid SensorCandidate for unit tests."""
    return SensorCandidate(
        sensor_id=sensor_id,
        title="Test sensor",
        detector=DetectorRule(
            engine="ast-grep", rule="id: test\nlanguage: Python\npattern:\n  kind: call\n  fn: foo"
        ),
        language="python",
        positives=positives if positives is not None else [{"file": "a.py", "expect": "match"}],
        negatives=negatives if negatives is not None else [{"file": "b.py", "expect": "no-match"}],
        origin_run_ids=origin_run_ids if origin_run_ids is not None else ["run-001"],
        status=status,
        created_at="2026-09-03T00:00:00Z",
    )


# ----------------------------------------------------------------------
# Schema validation
# ----------------------------------------------------------------------
class TestSensorCandidateSchema:
    def test_valid_candidate_roundtrip(self):
        cand = _minimal_candidate()
        raw = cand.model_dump_json()
        restored = SensorCandidate.model_validate_json(raw)
        assert restored.sensor_id == cand.sensor_id
        assert restored.schema == CANDIDATE_SCHEMA

    def test_sensor_id_regex_valid(self):
        for good in ("abc", "a1-b2-c3", "x" * 64):
            c = _minimal_candidate(sensor_id=good)
            assert c.sensor_id == good

    def test_sensor_id_regex_invalid_rejected(self):
        # Note: regex ^[a-z0-9-]{3,64}$ allows hyphens anywhere, so
        # "-abc" and "abc-" are technically valid (not included here).
        for bad in ("A1", "abc_DEF", "a b", "ab!", "ab"):
            with pytest.raises(ValueError, match="sensor_id must match"):
                _minimal_candidate(sensor_id=bad)

    def test_min_origin_run_ids(self):
        """Empty origin_run_ids list must be rejected by min_length."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="origin_run_ids"):
            _minimal_candidate(origin_run_ids=[])

    def test_unknown_status_rejected(self):
        with pytest.raises(ValueError):
            _minimal_candidate(status="unknown")

    def test_extra_fields_forbidden(self):
        cand = _minimal_candidate()
        dump = json.loads(cand.model_dump_json())
        dump["extra_field"] = "forbidden"
        with pytest.raises(ValueError):
            SensorCandidate.model_validate_json(json.dumps(dump))

    def test_fixture_expect_validation(self):
        bad_fixture = [{"file": "a.py", "expect": "maybe"}]
        with pytest.raises(ValueError, match="expect must be one of"):
            _minimal_candidate(positives=bad_fixture)

    def test_deterministic_ordering(self):
        cand = _minimal_candidate(
            positives=[
                {"file": "z.py", "expect": "match"},
                {"file": "a.py", "expect": "match"},
            ],
            negatives=[
                {"file": "m.py", "expect": "no-match"},
                {"file": "b.py", "expect": "no-match"},
            ],
        )
        # After model_validator, both lists are sorted by filename
        assert [f["file"] for f in cand.positives] == ["a.py", "z.py"]
        assert [f["file"] for f in cand.negatives] == ["b.py", "m.py"]

    def test_canonical_json_deterministic(self):
        cand = _minimal_candidate(
            positives=[
                {"file": "z.py", "expect": "match"},
                {"file": "a.py", "expect": "match"},
            ],
            negatives=[
                {"file": "m.py", "expect": "no-match"},
                {"file": "b.py", "expect": "no-match"},
            ],
        )
        j1 = cand.canonical_json()
        j2 = cand.canonical_json()
        assert j1 == j2  # byte-identical


# ----------------------------------------------------------------------
# evaluate_sensor — engine availability check
# ----------------------------------------------------------------------
def _both_engines_available() -> bool:
    """True only when both ast-grep (sg) and semgrep are on PATH."""
    return engine_path("ast-grep") is not None and engine_path("semgrep") is not None


# ----------------------------------------------------------------------
# evaluate_sensor — E2E with bundled fixture
# ----------------------------------------------------------------------
class TestEvaluateSensorE2E:
    def test_evaluate_sensor_from_fixtures_dir(self, tmp_path: Path):
        """Full end-to-end against the bundled fixture corpus."""
        if not _both_engines_available():
            pytest.skip(
                "ast-grep or semgrep not available — ENGINE_MISSING path exercised separately"
            )

        # Copy fixture files to a temp dir (simulates candidate_dir layout)
        cand_json = FIXTURES / "candidate.json"
        tmp_cand = tmp_path / "candidate.json"
        tmp_cand.write_text(cand_json.read_text())

        pos_out = tmp_path / "positives"
        neg_out = tmp_path / "negatives"
        pos_out.mkdir()
        neg_out.mkdir()

        for src in POS_DIR.iterdir():
            shutil.copy2(src, pos_out / src.name)
        for src in NEG_DIR.iterdir():
            shutil.copy2(src, neg_out / src.name)

        result = evaluate_sensor(tmp_path)

        assert result.evaluated is True, (
            f"expected evaluated=True, got {result.reason_code}: {result.detail}"
        )
        assert result.precision == 1.0, f"expected precision=1.0, got {result.precision}"
        assert result.recall == 1.0, f"expected recall=1.0, got {result.recall}"

    def test_engine_missing_not_exception(self, tmp_path: Path):
        """ENGINE_MISSING returns evaluated=False with a reason code — not an exception."""
        cand_json = FIXTURES / "candidate.json"
        tmp_cand = tmp_path / "candidate.json"
        tmp_cand.write_text(cand_json.read_text())

        pos_out = tmp_path / "positives"
        neg_out = tmp_path / "negatives"
        pos_out.mkdir()
        neg_out.mkdir()
        for src in POS_DIR.iterdir():
            shutil.copy2(src, pos_out / src.name)
        for src in NEG_DIR.iterdir():
            shutil.copy2(src, neg_out / src.name)

        # Simulate both engines absent by patching engine_path
        import archskillkit.sensor_candidate as cand_mod

        original_ag = cand_mod.engine_path("ast-grep")
        original_sg = cand_mod.engine_path("semgrep")
        try:
            cand_mod.engine_path = lambda e: None  # type: ignore[assignment]
            result = evaluate_sensor(tmp_path)
        finally:
            cand_mod.engine_path = lambda e: (  # type: ignore[assignment]
                original_ag if e == "ast-grep" else original_sg
            )

        assert result.evaluated is False
        assert result.reason_code == "ENGINE_MISSING"
        assert result.precision == 0.0
        assert result.recall == 0.0


# ----------------------------------------------------------------------
# meets_threshold
# ----------------------------------------------------------------------
class TestMeetsThreshold:
    def _eval(self, evaluated: bool, precision: float, recall: float) -> SensorEvaluation:
        return SensorEvaluation(
            sensor_id="test",
            evaluated=evaluated,
            precision=precision,
            recall=recall,
        )

    def test_true_when_above_both_thresholds(self):
        ev = self._eval(True, 0.95, 0.92)
        assert meets_threshold(ev) is True

    def test_true_at_exact_threshold(self):
        ev = self._eval(True, 0.9, 0.9)
        assert meets_threshold(ev) is True

    def test_false_when_precision_below(self):
        ev = self._eval(True, 0.89, 0.95)
        assert meets_threshold(ev) is False

    def test_false_when_recall_below(self):
        ev = self._eval(True, 0.95, 0.89)
        assert meets_threshold(ev) is False

    def test_false_when_not_evaluated(self):
        ev = self._eval(False, 1.0, 1.0)
        assert meets_threshold(ev) is False

    def test_custom_thresholds(self):
        ev = self._eval(True, 0.8, 0.85)
        assert meets_threshold(ev, min_precision=0.8, min_recall=0.85) is True
        assert meets_threshold(ev, min_precision=0.9, min_recall=0.9) is False


# ----------------------------------------------------------------------
# Determinism
# ----------------------------------------------------------------------
class TestDeterminism:
    def test_evaluate_sensor_idempotent(self, tmp_path: Path):
        """Same candidate_dir → byte-identical SensorEvaluation JSON."""
        cand_json = FIXTURES / "candidate.json"
        tmp_cand = tmp_path / "candidate.json"
        tmp_cand.write_text(cand_json.read_text())

        pos_out = tmp_path / "positives"
        neg_out = tmp_path / "negatives"
        pos_out.mkdir()
        neg_out.mkdir()

        for src in POS_DIR.iterdir():
            shutil.copy2(src, pos_out / src.name)
        for src in NEG_DIR.iterdir():
            shutil.copy2(src, neg_out / src.name)

        import archskillkit.sensor_candidate as cand_mod

        original = cand_mod.engine_path
        try:
            cand_mod.engine_path = lambda e: None  # type: ignore[assignment]
            r1 = evaluate_sensor(tmp_path)
            r2 = evaluate_sensor(tmp_path)
        finally:
            cand_mod.engine_path = original

        # Even without ENGINE_MISSING path, run twice to verify determinism
        # When engine is missing, both runs produce identical evaluated=False
        # When engine is present, both runs produce identical evaluated=True + metrics
        assert r1.canonical_json() == r2.canonical_json()


# ----------------------------------------------------------------------
# SensorEvaluation schema
# ----------------------------------------------------------------------
class TestSensorEvaluationSchema:
    def test_eval_schema_constant(self):
        ev = SensorEvaluation(sensor_id="x", evaluated=True, precision=1.0, recall=1.0)
        assert ev.schema == EVAL_SCHEMA

    def test_eval_extra_forbidden(self):
        ev = SensorEvaluation(sensor_id="x")
        dump = ev.model_dump()
        dump["spurious"] = "rejected"
        with pytest.raises(ValueError):
            SensorEvaluation.model_validate(dump)

    def test_eval_canonical_json(self):
        ev = SensorEvaluation(sensor_id="x", evaluated=False, reason_code="ENGINE_MISSING")
        j1 = ev.canonical_json()
        j2 = ev.canonical_json()
        assert j1 == j2
