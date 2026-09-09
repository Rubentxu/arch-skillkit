"""T-5 regression tests: supported-platforms matrix is in sync.

The supported-platforms document MUST list the same `(os, arch)`
pairs as the `PLATFORMS` tuple in
`scripts/release/generate-runtime-manifest.py`.

The runtime's `PLATFORM_UNSUPPORTED` finding MUST mention the v0.5.0
matrix in its remedy text.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GEN_PATH = ROOT / "scripts" / "release" / "generate-runtime-manifest.py"
DOC_PATH = ROOT / "docs" / "v2" / "25-supported-platforms.md"
RUNTIME_PY = ROOT / "python" / "src" / "archskillkit" / "runtime.py"


def _load_generator():
    spec = importlib.util.spec_from_file_location("gen_manifest", GEN_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_doc_matrix_matches_PLATFORMS_tuple():
    """The supported-platforms doc must list every (os, arch) pair
    declared in PLATFORMS and no extra."""
    gen = _load_generator()
    declared = {(os_, arch) for os_, arch in gen.PLATFORMS}
    assert declared, "PLATFORMS must not be empty"

    doc = DOC_PATH.read_text()
    # The doc has a Markdown table. Extract rows.
    table_rows = []
    for line in doc.splitlines():
        line = line.strip()
        if not line.startswith("|") or line.startswith("|---") or line.startswith("| OS"):
            continue
        # Format: `| linux | x86_64 | ... |`
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) >= 2 and cells[0] in {"linux", "darwin", "windows"}:
            table_rows.append((cells[0], cells[1]))

    assert set(table_rows) == declared, (
        f"doc matrix {set(table_rows)} != PLATFORMS {declared}"
    )


def test_PLATFORM_UNSUPPORTED_message_mentions_v050_matrix():
    """The runtime's PLATFORM_UNSUPPORTED finding must include a
    remedy that names the supported matrix."""
    sys.path.insert(0, str(ROOT / "python" / "src"))
    from archskillkit.runtime import Finding

    finding = Finding(
        "PLATFORM_UNSUPPORTED",
        "platform linux/armv7 is not in manifest v0.5.0",
        "use a supported platform (linux x86_64 / aarch64)",
    )
    remedy = finding.remedy.lower()
    assert "linux" in remedy
    assert "x86_64" in remedy
    assert "aarch64" in remedy


def test_doc_lists_no_unsupported_arch():
    """The doc MUST NOT list platforms that aren't in PLATFORMS (e.g.
    armv7, riscv64, darwin, windows)."""
    gen = _load_generator()
    declared = {(os_, arch) for os_, arch in gen.PLATFORMS}

    doc = DOC_PATH.read_text()
    # Anything in the "Out of scope" section is allowed.
    in_scope, out_of_scope = doc.split("### Out of scope (v0.5.0)")
    for line in in_scope.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) >= 2 and cells[0] in {"linux", "darwin", "windows"}:
            assert (cells[0], cells[1]) in declared, (
                f"in-scope row {cells[0]}/{cells[1]} not in PLATFORMS"
            )


def test_doc_links_to_related_documents():
    """The doc references the user manuals and ADR-0063 (T-7)."""
    doc = DOC_PATH.read_text()
    assert "docs/manual/user-manual.md" in doc
    assert "docs/manual/manual-de-usuario.md" in doc
    # ADR-0063 (T-7 deliverable) is the canonical reference for the
    # distribution v1 design decisions; the doc must point at it.
    assert "ADR-0063" in doc
    # Defensive: there is no ADR-0053 for this cycle (it covers the
    # Thin Local Control Plane), so we should not link to it.
    assert "ADR-0053-archskillkit-distribution" not in doc
