"""V2.4 M6 slice 29 — Sensor Distiller tests.

In-process world fixtures (no git required for the distiller itself).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from archskillkit.packs.arch_core import ClaimData
from archskillkit.sensor_distiller import _derive_signature, _make_sensor_id, distill
from archskillkit.world import ArchitectureWorld

# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _git_out(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture()
def sandbox_world(tmp_path):
    """Minimal in-process ArchitectureWorld with no external git deps."""
    data = tmp_path / "data"
    state = tmp_path / "state"
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "src").mkdir()
    (repo / "src" / "main.py").write_text("def main(): pass\n")
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "remote", "add", "origin", "https://example.com/test.git")

    import os

    old_data = os.environ.get("XDG_DATA_HOME")
    old_state = os.environ.get("XDG_STATE_HOME")
    try:
        os.environ["XDG_DATA_HOME"] = str(data)
        os.environ["XDG_STATE_HOME"] = str(state)
        world = ArchitectureWorld.for_repo(repo)
        world.open()
        yield world
    finally:
        world.close()
        if old_data is not None:
            os.environ["XDG_DATA_HOME"] = old_data
        elif "XDG_DATA_HOME" in os.environ:
            del os.environ["XDG_DATA_HOME"]
        if old_state is not None:
            os.environ["XDG_STATE_HOME"] = old_state
        elif "XDG_STATE_HOME" in os.environ:
            del os.environ["XDG_STATE_HOME"]


# ----------------------------------------------------------------------
# Signature helpers — unit tests
# ----------------------------------------------------------------------


class TestSignatureDerivation:
    def test_derive_signature_stable(self):
        claim = {
            "origin": "INFERRED",
            "statement": "orders service exposes a REST API",
            "subjects": ["orders", "api"],
        }
        sig = _derive_signature(claim)
        assert sig == (("api", "orders"), "orders service exposes a rest api")

    def test_derive_signature_subjects_sorted(self):
        """Subject ordering must NOT affect the signature."""
        c1 = {"statement": "foo", "subjects": ["b", "a"]}
        c2 = {"statement": "foo", "subjects": ["a", "b"]}
        assert _derive_signature(c1) == _derive_signature(c2)

    def test_derive_signature_statement_normalised(self):
        """Extra whitespace / case must NOT affect the signature."""
        c1 = {"statement": "  Hello   World  ", "subjects": ["x"]}
        c2 = {"statement": "hello world", "subjects": ["x"]}
        assert _derive_signature(c1) == _derive_signature(c2)

    def test_make_sensor_id_deterministic(self):
        sig = (("api",), "orders service exposes rest api")
        id1 = _make_sensor_id(sig)
        id2 = _make_sensor_id(sig)
        assert id1 == id2

    def test_make_sensor_id_matches_regex(self):
        import re

        SENSOR_ID_RE = r"^[a-z0-9-]{3,64}$"
        sig = (("orders",), "orders service exposes rest api")
        sid = _make_sensor_id(sig)
        assert re.match(SENSOR_ID_RE, sid), f"sensor_id {sid!r} does not match {SENSOR_ID_RE}"

    def test_make_sensor_id_starts_with_inferred(self):
        sig = (("orders",), "orders service exposes rest api")
        sid = _make_sensor_id(sig)
        assert sid.startswith("inferred-")

    def test_make_sensor_id_includes_subject(self):
        """First subject should appear in sensor_id."""
        sig = (("orders",), "orders service exposes rest api")
        sid = _make_sensor_id(sig)
        assert "orders" in sid


# ----------------------------------------------------------------------
# Core distillation logic
# ----------------------------------------------------------------------


class TestDistillBasic:
    def test_single_run_not_distilled(self, sandbox_world):
        """A signature appearing in only 1 run must NOT produce a candidate."""
        sandbox_world.propose_claim(
            ClaimData(
                statement="orders is a bounded context",
                subjects=["orders"],
                origin="INFERRED",
            )
        )

        candidates = distill(sandbox_world, min_runs=2, min_occurrences=1)
        assert candidates == []

    def test_two_runs_below_min_occurrences(self, sandbox_world):
        """min_occurrences=2 but only 1 total claim → no candidate."""
        sandbox_world.propose_claim(
            ClaimData(
                statement="orders is a bounded context",
                subjects=["orders"],
                origin="INFERRED",
            )
        )
        fork = sandbox_world.fork("orders-proposal")
        fork.propose_claim(
            ClaimData(
                statement="orders is a bounded context",
                subjects=["orders"],
                origin="INFERRED",
            )
        )

        # Run distiller on the main world (fork's claims are accessible via list_runs)
        candidates = distill(sandbox_world, min_runs=1, min_occurrences=2)
        assert len(candidates) == 1
        assert candidates[0].sensor_id.startswith("inferred-")
        assert candidates[0].status == "candidate"
        assert candidates[0].origin_run_ids == sorted(candidates[0].origin_run_ids)

    def test_two_runs_above_thresholds(self, sandbox_world):
        """Same signature in 2 runs with >=2 total claims → candidate emitted."""
        # Run 1 (main)
        sandbox_world.propose_claim(
            ClaimData(
                statement="orders is a bounded context",
                subjects=["orders"],
                origin="INFERRED",
            )
        )
        sandbox_world.propose_claim(
            ClaimData(
                statement="payments exposes webhook endpoint",
                subjects=["payments"],
                origin="INFERRED",
            )
        )

        # Fork run — same orders claim repeated
        fork = sandbox_world.fork("orders-proposal")
        fork.propose_claim(
            ClaimData(
                statement="orders is a bounded context",
                subjects=["orders"],
                origin="INFERRED",
            )
        )

        candidates = distill(sandbox_world, min_runs=2, min_occurrences=2)
        assert len(candidates) == 1
        cand = candidates[0]
        assert "orders" in cand.sensor_id
        assert set(cand.origin_run_ids) == {"world", "proposal-orders-proposal"}
        assert cand.positives == []
        assert cand.negatives == []
        assert cand.status == "candidate"
        assert cand.metrics.get("evaluated") is False

    def test_detected_origin_not_distilled(self, sandbox_world):
        """DETECTED claims must be ignored by the distiller."""
        sandbox_world.propose_claim(
            ClaimData(
                statement="this is a deterministic scan finding",
                subjects=["orders"],
                origin="DETECTED",
            )
        )
        candidates = distill(sandbox_world, min_runs=1, min_occurrences=1)
        assert candidates == []

    def test_multiple_signatures_produce_multiple_candidates(self, sandbox_world):
        """Different INFERRED signatures → separate candidates."""
        sandbox_world.propose_claim(
            ClaimData(
                statement="orders is a bounded context",
                subjects=["orders"],
                origin="INFERRED",
            )
        )
        sandbox_world.propose_claim(
            ClaimData(
                statement="payments is a bounded context",
                subjects=["payments"],
                origin="INFERRED",
            )
        )

        candidates = distill(sandbox_world, min_runs=1, min_occurrences=1)
        assert len(candidates) == 2
        sensor_ids = [c.sensor_id for c in candidates]
        assert len(set(sensor_ids)) == 2  # distinct

    def test_origin_run_ids_sorted_and_unique(self, sandbox_world):
        """origin_run_ids must be sorted without duplicates."""
        sandbox_world.propose_claim(
            ClaimData(
                statement="orders is a bounded context",
                subjects=["orders"],
                origin="INFERRED",
            )
        )
        fork_a = sandbox_world.fork("alpha")
        fork_b = sandbox_world.fork("beta")
        fork_a.propose_claim(
            ClaimData(
                statement="orders is a bounded context",
                subjects=["orders"],
                origin="INFERRED",
            )
        )
        fork_b.propose_claim(
            ClaimData(
                statement="orders is a bounded context",
                subjects=["orders"],
                origin="INFERRED",
            )
        )

        candidates = distill(sandbox_world, min_runs=2, min_occurrences=2)
        assert len(candidates) == 1
        run_ids = candidates[0].origin_run_ids
        assert run_ids == sorted(run_ids)  # sorted
        assert len(run_ids) == len(set(run_ids))  # unique

    def test_determinism_same_world_twice(self, sandbox_world):
        """Two calls on the same world state → identical candidate JSON."""
        sandbox_world.propose_claim(
            ClaimData(
                statement="orders is a bounded context",
                subjects=["orders"],
                origin="INFERRED",
            )
        )

        c1 = distill(sandbox_world, min_runs=1, min_occurrences=1)
        c2 = distill(sandbox_world, min_runs=1, min_occurrences=1)
        assert len(c1) == len(c2)
        for a, b in zip(c1, c2):
            assert a.canonical_json() == b.canonical_json()

    def test_world_not_mutated(self, sandbox_world):
        """Claim counts must be identical before and after distillation."""
        sandbox_world.propose_claim(
            ClaimData(
                statement="orders is a bounded context",
                subjects=["orders"],
                origin="INFERRED",
            )
        )

        before = sandbox_world.snapshot()
        distill(sandbox_world, min_runs=1, min_occurrences=1)
        after = sandbox_world.snapshot()

        assert before["counts"] == after["counts"]
        assert before["objects"].keys() == after["objects"].keys()

    def test_min_occurrences_boundary(self, sandbox_world):
        """Exactly min_occurrences must be included."""
        sandbox_world.propose_claim(
            ClaimData(
                statement="orders is a bounded context",
                subjects=["orders"],
                origin="INFERRED",
            )
        )
        fork = sandbox_world.fork("p")
        fork.propose_claim(
            ClaimData(
                statement="orders is a bounded context",
                subjects=["orders"],
                origin="INFERRED",
            )
        )

        # Exactly 2 occurrences, min_runs=2
        candidates = distill(sandbox_world, min_runs=2, min_occurrences=2)
        assert len(candidates) == 1

        # Below threshold: need 3 occurrences
        candidates = distill(sandbox_world, min_runs=2, min_occurrences=3)
        assert candidates == []

    def test_min_runs_boundary(self, sandbox_world):
        """Exactly min_runs must be included."""
        sandbox_world.propose_claim(
            ClaimData(
                statement="orders is a bounded context",
                subjects=["orders"],
                origin="INFERRED",
            )
        )
        fork = sandbox_world.fork("p")
        fork.propose_claim(
            ClaimData(
                statement="orders is a bounded context",
                subjects=["orders"],
                origin="INFERRED",
            )
        )

        candidates = distill(sandbox_world, min_runs=2, min_occurrences=1)
        assert len(candidates) == 1

        candidates = distill(sandbox_world, min_runs=3, min_occurrences=1)
        assert candidates == []

    def test_invalid_thresholds_raise(self, sandbox_world):
        with pytest.raises(ValueError, match="min_runs and min_occurrences must be >= 1"):
            distill(sandbox_world, min_runs=0, min_occurrences=1)
        with pytest.raises(ValueError, match="min_runs and min_occurrences must be >= 1"):
            distill(sandbox_world, min_runs=1, min_occurrences=0)


class TestSensorIdRegexCompliance:
    """sensor_id must pass the same regex as SensorCandidate validator."""

    def test_all_generated_ids_match_regex(self, sandbox_world):
        sandbox_world.propose_claim(
            ClaimData(
                statement="orders is a bounded context",
                subjects=["orders-service"],
                origin="INFERRED",
            )
        )
        sandbox_world.propose_claim(
            ClaimData(
                statement="payments uses stripe",
                subjects=["payments"],
                origin="INFERRED",
            )
        )

        candidates = distill(sandbox_world, min_runs=1, min_occurrences=1)
        import re

        SENSOR_ID_RE = r"^[a-z0-9-]{3,64}$"
        for c in candidates:
            assert re.match(SENSOR_ID_RE, c.sensor_id), f"{c.sensor_id!r} fails {SENSOR_ID_RE}"


class TestCandidateStructure:
    def test_candidate_has_required_fields(self, sandbox_world):
        sandbox_world.propose_claim(
            ClaimData(
                statement="orders is a bounded context",
                subjects=["orders"],
                origin="INFERRED",
            )
        )

        [c] = distill(sandbox_world, min_runs=1, min_occurrences=1)
        assert c.schema == "arch-skillkit/sensor-candidate-v1"
        assert c.detector.engine == "ast-grep"
        assert "rule" in c.detector.model_dump()
        assert c.status == "candidate"
        assert c.created_at  # non-empty string
        assert c.metrics["evaluated"] is False

    def test_positives_negatives_are_empty_lists(self, sandbox_world):
        """Distiller proposes; humans curate fixtures later (docs/v2/53)."""
        sandbox_world.propose_claim(
            ClaimData(
                statement="orders is a bounded context",
                subjects=["orders"],
                origin="INFERRED",
            )
        )

        [c] = distill(sandbox_world, min_runs=1, min_occurrences=1)
        assert c.positives == []
        assert c.negatives == []
