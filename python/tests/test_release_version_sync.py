"""T-1 regression tests: single source of truth for version surfaces.

Every version surface MUST agree with python/pyproject.toml::version:

- skills/architecture-discovery/version.json::skill_version
- the installed __version__ (after `pip install -e python` or wheel install)
- the wheel filename in dist/ or python/dist/

Run `python -m pytest tests/test_release_version_sync.py -v`.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = ROOT / "python" / "pyproject.toml"
VERSION_JSON = ROOT / "skills" / "architecture-discovery" / "version.json"
SYNC = ROOT / "scripts" / "release" / "sync-versions.py"


def _pyproject_version() -> str:
    text = PYPROJECT.read_text()
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
    assert m, "pyproject.toml must declare a version= field"
    return m.group(1)


def test_version_surfaces_agree():
    declared = _pyproject_version()

    # Surface 1: version.json
    data = json.loads(VERSION_JSON.read_text())
    assert data["skill_version"] == declared, (
        f"version.json::skill_version={data['skill_version']!r} "
        f"!= pyproject {declared!r}"
    )

    # Surface 2: installed __version__ (resolves importlib.metadata)
    import archskillkit  # noqa: PLC0415
    assert archskillkit.__version__ == declared, (
        f"installed __version__={archskillkit.__version__!r} "
        f"!= pyproject {declared!r}"
    )


def test_sync_versions_check_passes_on_clean_tree():
    declared = _pyproject_version()
    proc = subprocess.run(
        [sys.executable, str(SYNC), "--check"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, (
        f"sync-versions --check exited {proc.returncode}\n"
        f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
    )
    assert f"declared version (pyproject.toml): {declared}" in proc.stdout
    assert "OK: version.json skill_version ==" in proc.stdout
    assert "OK: installed __version__ ==" in proc.stdout


def test_sync_versions_check_detects_drift(tmp_path: Path):
    """Mutate version.json to simulate drift; assert --check exits non-zero."""
    declared = _pyproject_version()
    broken = json.loads(VERSION_JSON.read_text())
    original = broken["skill_version"]
    broken["skill_version"] = f"{declared}-broken"
    try:
        VERSION_JSON.write_text(json.dumps(broken, indent=2, ensure_ascii=False))
        proc = subprocess.run(
            [sys.executable, str(SYNC), "--check"],
            capture_output=True, text=True,
        )
        assert proc.returncode != 0, (
            f"sync-versions --check should fail on drift, but exited 0\n"
            f"stdout: {proc.stdout}"
        )
        assert "ERROR:" in proc.stdout
        assert "broken" in proc.stdout
    finally:
        restored = json.loads(VERSION_JSON.read_text())
        restored["skill_version"] = original
        VERSION_JSON.write_text(
            json.dumps(restored, indent=2, ensure_ascii=False)
        )


def test_sync_versions_autofix_restores(tmp_path: Path):
    """Without --check, sync-versions should auto-fix version.json drift."""
    declared = _pyproject_version()
    broken = json.loads(VERSION_JSON.read_text())
    original = broken["skill_version"]
    broken["skill_version"] = "9.9.9-drift"
    try:
        VERSION_JSON.write_text(json.dumps(broken, indent=2, ensure_ascii=False))
        proc = subprocess.run(
            [sys.executable, str(SYNC)],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0, proc.stderr
        assert "synced version.json skill_version" in proc.stdout
        # Verify fix
        after = json.loads(VERSION_JSON.read_text())
        assert after["skill_version"] == declared
    finally:
        restored = json.loads(VERSION_JSON.read_text())
        restored["skill_version"] = original
        VERSION_JSON.write_text(
            json.dumps(restored, indent=2, ensure_ascii=False)
        )


def test_init_version_is_derived_from_metadata():
    """`__init__.py` MUST derive __version__ from importlib.metadata.

    This catches a regression where someone hard-codes the literal back.
    """
    import archskillkit  # noqa: PLC0415
    src = (ROOT / "python" / "src" / "archskillkit" / "__init__.py").read_text()
    assert "importlib.metadata" in src, (
        "__init__.py must derive __version__ from importlib.metadata "
        "(single source of truth — see T-1 of archskillkit-distribution-v1)"
    )
    # And the resolved value must equal pyproject.
    assert archskillkit.__version__ == _pyproject_version()
