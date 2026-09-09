"""T-4 regression tests: attestation policy in the runtime manifest.

The manifest generator MUST emit:

* `attestation.required=True` for artifacts we sign ourselves
  (likec4, semgrep), with the `attestation.repository` field.
* `attestation.required=False` for upstream artifacts (ast-grep, node),
  plus a `warning` field that explains the integrity guarantee is
  hash-only and there is no provenance attestation by us.

The runtime manifest model MUST accept the new `warning` field on
`AttestationPolicy`.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GEN_PATH = ROOT / "scripts" / "release" / "generate-runtime-manifest.py"
MODEL_PATH = ROOT / "python" / "src" / "archskillkit" / "runtime_manifest.py"


def _load_generator():
    spec = importlib.util.spec_from_file_location("gen_manifest", GEN_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _artifact_upstream() -> dict:
    """An upstream (non-self-attested) artifact entry."""
    return _load_generator().artifact(
        "ast-grep", "binary", "0.39.0",
        "https://example.invalid/ast-grep.zip",
        "deadbeef" * 8, 1024,
        executable="ast-grep", license_id="MIT",
    )


def _artifact_self_attested() -> dict:
    """A self-attested artifact entry."""
    return _load_generator().artifact(
        "likec4", "npm-bundle", "1.0.0",
        "https://example.invalid/likec4.tgz",
        "feedface" * 8, 2048,
        executable=None, license_id="MIT",
        attested_by_us=True, attestation_repo="Rubentxu/arch-skillkit",
    )


def test_upstream_artifact_required_false_with_warning():
    entry = _artifact_upstream()
    assert entry["attestation"]["required"] is False
    assert "warning" in entry["attestation"]
    # Be liberal about the exact wording; assert the substance.
    warning = entry["attestation"]["warning"].lower()
    assert "sha256" in warning
    assert "no provenance" in warning


def test_self_attested_artifact_required_true_with_repo():
    entry = _artifact_self_attested()
    assert entry["attestation"]["required"] is True
    assert entry["attestation"]["repository"] == "Rubentxu/arch-skillkit"
    assert "warning" not in entry["attestation"]


def test_artifact_model_accepts_warning_field():
    """The pydantic model accepts the new `warning` field on the
    policy without complaining about extra fields."""
    sys.path.insert(0, str(ROOT / "python" / "src"))
    from archskillkit.runtime_manifest import (
        AttestationPolicy, Artifact,
    )

    policy = AttestationPolicy(
        required=False,
        warning="upstream artifact; integrity verified by sha256 only",
    )
    assert policy.warning.startswith("upstream artifact")

    artifact = Artifact(
        id="ast-grep", kind="binary", version="0.39.0",
        url="https://example.invalid/ast-grep.zip",
        sha256="a" * 64, size_bytes=1024,
        executable="ast-grep", license="MIT",
        attestation=policy,
    )
    assert artifact.attestation.required is False
    assert artifact.attestation.warning is not None


def test_attestation_warning_is_serializable_round_trip():
    """The model can be round-tripped via JSON preserving the warning."""
    entry = _artifact_upstream()
    blob = json.dumps(entry)
    parsed = json.loads(blob)
    assert parsed["attestation"]["required"] is False
    assert "warning" in parsed["attestation"]
