"""T-7 regression tests: ADR-0063 covers the distribution v1 cycle.

ADR-0063 MUST exist, reference the cycle ID, and document the seven
decisions D-1..D-7 enumerated in design.md.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ADR = (
    ROOT / "docs" / "v2" / "adr" / "ADR-0063-archskillkit-distribution-v1.md"
)
ADR_DIR = ROOT / "docs" / "v2" / "adr"


def _all_adr_ids() -> set[str]:
    out = set()
    for path in ADR_DIR.glob("ADR-*.md"):
        m = re.match(r"ADR-(\d{4})", path.name)
        if m:
            out.add(m.group(1))
    return out


def test_adr_0063_exists():
    assert ADR.is_file(), f"missing {ADR}"


def test_adr_0063_is_not_a_duplicate_id():
    """No two ADRs may share the same numeric prefix."""
    ids = _all_adr_ids()
    assert "0063" in ids
    # 0063 must appear exactly once.
    occurrences = list(ADR_DIR.glob("ADR-0063-*.md"))
    assert len(occurrences) == 1, occurrences


def test_adr_0063_references_cycle_id():
    text = ADR.read_text()
    assert "p-f58d41952fdf56c1" in text, "ADR must name the cycle ID"


def test_adr_0063_documents_decisions():
    """ADR must name every decision D-1..D-7 in design.md."""
    text = ADR.read_text()
    for i in range(1, 8):
        assert f"D-{i}" in text, f"missing decision D-{i} in ADR-0063"


def test_adr_0063_documents_evidence():
    """ADR must list at least 6 test files as verification evidence."""
    text = ADR.read_text()
    matches = re.findall(r"python/tests/test_[a-z_]+\.py", text)
    assert len(set(matches)) >= 6, (
        f"expected >=6 test files referenced, got {set(matches)}"
    )


def test_adr_0063_status_accepted():
    text = ADR.read_text()
    assert re.search(r"^Status:\s*Accepted", text, re.M), (
        "ADR-0063 must be marked Status: Accepted"
    )
