"""T-6 regression tests: lint gate wires `sync-versions.py --check`.

`mise run lint` (declared in `mise.toml`) MUST include a non-comment
invocation of `python3 scripts/release/sync-versions.py --check` so
that drift in any of the three version surfaces (version.json, wheel
filenames in dist/, installed __version__) blocks the lint gate.

The script itself MUST exit non-zero when `--check` is used and any
declared surface (version.json skill_version, wheel filename) is out
of sync.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MISE_TOML = ROOT / "mise.toml"
SYNC = ROOT / "scripts" / "release" / "sync-versions.py"
VERSION_JSON = (
    ROOT / "skills" / "architecture-discovery" / "version.json"
)
PYPROJECT = ROOT / "python" / "pyproject.toml"


def _mise_lint_section() -> str:
    """Return the body of the [tasks.lint] block in mise.toml."""
    text = MISE_TOML.read_text()
    start = text.index("[tasks.lint]")
    end = text.index("\n[", start + 1)
    return text[start:end]


def test_lint_invokes_sync_versions_check():
    """`mise run lint` must invoke sync-versions.py --check."""
    section = _mise_lint_section()
    assert "sync-versions.py" in section
    assert "--check" in section


def _run_sync(target: Path, cwd: Path) -> subprocess.CompletedProcess:
    """Run sync-versions.py in an isolated environment (no global
    archskillkit installation leaks in)."""
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(cwd),
        "PYTHONNOUSERSITE": "1",
        # Point PYTHONPATH to an empty scratch dir; no archskillkit there.
        "PYTHONPATH": "",
    }
    return subprocess.run(
        ["python3", str(target), "--check"],
        capture_output=True, text=True, cwd=cwd, env=env,
    )


def test_sync_versions_check_fails_on_version_json_drift(
    tmp_path: Path,
):
    """When version.json skill_version drifts from pyproject.toml
    and --check is set, the script exits non-zero."""
    # Build an isolated tree that mimics the repo layout.
    scripts = tmp_path / "scripts" / "release"
    scripts.mkdir(parents=True)
    skills = tmp_path / "skills" / "architecture-discovery"
    skills.mkdir(parents=True)
    python_dir = tmp_path / "python"
    python_dir.mkdir()

    (python_dir / "pyproject.toml").write_text('version = "9.9.9-test"\n')
    (skills / "version.json").write_text(json.dumps({
        "skill_version": "0.0.0-drift",
        "pinned_versions": {},
    }))

    # Copy sync-versions.py into our scratch tree.
    target = scripts / "sync-versions.py"
    target.write_text(SYNC.read_text())

    proc = _run_sync(target, tmp_path)
    assert proc.returncode != 0, (
        f"expected non-zero, got {proc.returncode}; stdout={proc.stdout}"
    )
    assert "version.json" in proc.stdout
    assert "9.9.9-test" in proc.stdout


def test_sync_versions_check_fails_on_wheel_filename_drift(
    tmp_path: Path,
):
    """When a wheel filename in dist/ has a different version than
    pyproject.toml and --check is set, the script exits non-zero."""
    scripts = tmp_path / "scripts" / "release"
    scripts.mkdir(parents=True)
    skills = tmp_path / "skills" / "architecture-discovery"
    skills.mkdir(parents=True)
    python_dir = tmp_path / "python"
    python_dir.mkdir()
    dist = tmp_path / "dist"
    dist.mkdir()

    (python_dir / "pyproject.toml").write_text('version = "0.5.0"\n')
    (skills / "version.json").write_text(json.dumps({
        "skill_version": "0.5.0",
        "pinned_versions": {},
    }))
    # An old wheel still on disk.
    (dist / "archskillkit-0.4.0-py3-none-any.whl").write_text("x")

    target = scripts / "sync-versions.py"
    target.write_text(SYNC.read_text())

    proc = _run_sync(target, tmp_path)
    assert proc.returncode != 0, (
        f"stdout={proc.stdout}\nstderr={proc.stderr}"
    )
    assert "wheel" in proc.stdout
    assert "0.4.0" in proc.stdout


def test_sync_versions_check_passes_when_in_sync(tmp_path: Path):
    """When all surfaces agree and --check is set, exit code is 0."""
    scripts = tmp_path / "scripts" / "release"
    scripts.mkdir(parents=True)
    skills = tmp_path / "skills" / "architecture-discovery"
    skills.mkdir(parents=True)
    python_dir = tmp_path / "python"
    python_dir.mkdir()
    dist = tmp_path / "dist"
    dist.mkdir()

    (python_dir / "pyproject.toml").write_text('version = "0.5.0"\n')
    (skills / "version.json").write_text(json.dumps({
        "skill_version": "0.5.0",
        "pinned_versions": {},
    }))
    (dist / "archskillkit-0.5.0-py3-none-any.whl").write_text("x")

    target = scripts / "sync-versions.py"
    target.write_text(SYNC.read_text())

    proc = _run_sync(target, tmp_path)
    assert proc.returncode == 0, (
        f"stdout={proc.stdout}\nstderr={proc.stderr}"
    )
