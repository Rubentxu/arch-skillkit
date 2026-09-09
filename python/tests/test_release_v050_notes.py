"""T-8 regression tests: v0.5.0 release notes are consistent.

The release notes document MUST exist, reference the cycle ID and
ADR-0063, and describe every task T-1..T-8.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
NOTES = ROOT / "docs" / "releases" / "v0.5.0.md"
ADR = (
    ROOT / "docs" / "v2" / "adr" / "ADR-0063-archskillkit-distribution-v1.md"
)
SUPPORTED = ROOT / "docs" / "v2" / "25-supported-platforms.md"


def test_release_notes_exist():
    assert NOTES.is_file()


def test_release_notes_reference_cycle_and_adr():
    text = NOTES.read_text()
    assert "p-f58d41952fdf56c1" in text
    assert "ADR-0063" in text


def test_release_notes_describe_all_tasks():
    text = NOTES.read_text()
    for i in range(1, 9):
        assert f"T-{i}" in text, f"missing T-{i} in release notes"


def test_release_notes_name_test_files():
    """Release notes list the 7 test files added by this cycle."""
    text = NOTES.read_text()
    expected_files = [
        "test_release_version_sync.py",
        "test_verify_version_default.py",
        "test_runtime_atomicity.py",
        "test_manifest_attestation.py",
        "test_supported_platforms_doc.py",
        "test_lint_version_gate.py",
        "test_adr_0063_distribution.py",
    ]
    for name in expected_files:
        assert name in text, f"missing {name} in release notes"


def test_release_notes_adr_and_platforms_doc_exist():
    """The two doc artifacts referenced in the release notes exist."""
    assert ADR.is_file()
    assert SUPPORTED.is_file()
