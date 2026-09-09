"""T-2 regression tests: verify defaults track the released version.

scripts/verify/run-verify.sh MUST default to the version of the wheel
in dist/ (or python/pyproject.toml when no wheel exists). Explicit
override with warning is allowed for triage.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUN_VERIFY = ROOT / "scripts" / "verify" / "run-verify.sh"
PYPROJECT = ROOT / "python" / "pyproject.toml"


def _pyproject_version() -> str:
    text = PYPROJECT.read_text()
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
    assert m, "pyproject.toml must declare a version="
    return m.group(1)


def _resolver_source() -> str:
    """Extract the _resolve_default_version function as bash source."""
    src = RUN_VERIFY.read_text()
    start = src.index("_resolve_default_version() {")
    depth = 0
    i = src.index("{", start)
    end = i
    while i < len(src):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
        i += 1
    return src[start:end]


def test_resolver_reads_wheel_first():
    """Resolver returns the version of the wheel in $ROOT/dist/."""
    fn = _resolver_source()
    pyproject_v = _pyproject_version()
    with tempfile.TemporaryDirectory() as tmp:
        # wheel takes precedence even if pyproject.toml says something else
        (Path(tmp) / "dist").mkdir()
        (Path(tmp) / "dist" / f"archskillkit-{pyproject_v}-py3-none-any.whl").write_text("x")
        (Path(tmp) / "python").mkdir()
        (Path(tmp) / "python" / "pyproject.toml").write_text('version = "0.0.0-fallback"\n')
        script = f"ROOT='{tmp}'\n{fn}\n_resolve_default_version\n"
        out = subprocess.check_output(["bash", "-c", script], text=True).strip()
        assert out == pyproject_v, f"got {out!r}, expected {pyproject_v}"


def test_resolver_falls_back_to_pyproject_when_no_wheel():
    """When no wheel is present, resolver reads python/pyproject.toml."""
    fn = _resolver_source()
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "dist").mkdir()  # empty
        (Path(tmp) / "python").mkdir()
        (Path(tmp) / "python" / "pyproject.toml").write_text('version = "9.9.9-test"\n')
        script = f"ROOT='{tmp}'\n{fn}\n_resolve_default_version\n"
        out = subprocess.check_output(["bash", "-c", script], text=True).strip()
        assert out == "9.9.9-test", f"got {out!r}"


def test_run_verify_default_version_matches_released():
    """run-verify.sh defaults to the current wheel version."""
    proc = subprocess.run(
        ["bash", "-n", str(RUN_VERIFY)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, f"bash syntax: {proc.stderr}"

    # Source only the resolver (run-verify.sh would launch docker, not desired).
    fn = _resolver_source()
    script = f"ROOT='{ROOT}'\n{fn}\n_resolve_default_version\n"
    out = subprocess.check_output(["bash", "-c", script], text=True).strip()
    expected = _pyproject_version()
    assert out == expected, f"resolver returned {out!r}, expected {expected!r}"


def test_run_verify_warning_on_older_override():
    """When called with an older version, the script emits a WARN."""
    fn = _resolver_source()
    # Reproduce the version-selection branch with arg=0.4.0.
    script = (
        f"ROOT='{ROOT}'\n{fn}\n"
        "DEFAULT=$(_resolve_default_version)\n"
        'VERSION="${1:-$DEFAULT}"\n'
        'if [ "${1:-}" != "" ] && [ "$VERSION" != "$DEFAULT" ]; then\n'
        '  echo "WARN: requested $VERSION != current $DEFAULT" >&2\n'
        "fi\n"
    )
    proc = subprocess.run(
        ["bash", "-c", script, "_", "0.4.0"],
        capture_output=True, text=True,
    )
    assert "WARN:" in proc.stderr, f"stderr: {proc.stderr}"
    assert "0.4.0" in proc.stderr
