#!/usr/bin/env python3
"""Keep every version surface in sync with python/pyproject.toml.

Decision D-2 (docs/v2/46): pyproject.toml is the single source of version
truth; every other surface is generated or asserted. T-1
(archskillkit-distribution-v1) extends the contract to include the wheel
filename and the installed `__version__` (after install). Run with --check
in gates to fail when any surface drifts:

    python3 scripts/release/sync-versions.py --check

Surfaces checked:

- python/pyproject.toml::version (authority)
- skills/architecture-discovery/version.json::skill_version
- python/src/archskillkit/__init__.py::__version__ (after install)
- dist/archskillkit-<version>-py3-none-any.whl filename (if present)
"""

from __future__ import annotations

import argparse
import importlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = ROOT / "python" / "pyproject.toml"
VERSION_JSON = ROOT / "skills" / "architecture-discovery" / "version.json"
WHEEL_GLOB = "archskillkit-*.whl"


def declared_version() -> str:
    text = PYPROJECT.read_text()
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
    if match is None:
        raise SystemExit(f"error: no version= found in {PYPROJECT}")
    return match.group(1)


def wheel_versions() -> dict[Path, str]:
    out: dict[Path, str] = {}
    # Match the wheel's version segment: starts with a digit, contains
    # alphanumerics, dots and dashes until the `-py3-none-any.whl`
    # suffix. `[^-]*` (not `[^.-]*`) so versions like `0.5.0` capture
    # the inner dots.
    pattern = re.compile(
        r"^archskillkit-([0-9][^-]*?)-py3-none-any\.whl$"
    )
    for dist_dir in (ROOT / "dist", ROOT / "python" / "dist"):
        if not dist_dir.exists():
            continue
        for whl in sorted(dist_dir.glob(WHEEL_GLOB)):
            m = pattern.match(whl.name)
            if m:
                out[whl] = m.group(1)
    return out


def installed_version() -> str | None:
    try:
        mod = importlib.import_module("archskillkit")
    except ImportError:
        return None
    v = getattr(mod, "__version__", None)
    if not isinstance(v, str):
        return None
    return v


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="fail instead of fixing when out of sync")
    args = parser.parse_args()

    version = declared_version()
    print(f"declared version (pyproject.toml): {version}")

    # Surface 1: version.json
    data = json.loads(VERSION_JSON.read_text())
    current = data.get("skill_version")
    if current != version:
        msg = (f"version.json::skill_version={current!r} != pyproject {version!r}")
        if args.check:
            print(f"ERROR: {msg}")
            return 1
        data["skill_version"] = version
        VERSION_JSON.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        )
        print(f"synced version.json skill_version -> {version}")
    else:
        print(f"OK: version.json skill_version == {version}")

    # Surface 2: wheel filename(s) in dist/
    wheels = wheel_versions()
    rc = 0
    for whl, v in wheels.items():
        if v != version:
            msg = f"wheel {whl.name} version={v!r} != pyproject {version!r}"
            if args.check:
                print(f"ERROR: {msg}")
                rc = 1
            else:
                print(f"WARN: {msg} (not removed automatically)")
                rc = 1
        else:
            print(f"OK: wheel {whl.name} matches {version}")

    # Surface 3: installed __version__ (informational; not fixable here)
    iv = installed_version()
    if iv is None:
        print("INFO: archskillkit not importable in current interpreter; "
              "skipping __version__ surface (run inside a venv with the wheel "
              "installed for full check)")
    elif iv == "0.0.0+unknown":
        print(f"WARN: archskillkit.__version__ = {iv!r} "
              "(source checkout without installed package)")
    elif iv != version:
        msg = f"installed __version__={iv!r} != pyproject {version!r}"
        if args.check:
            print(f"ERROR: {msg}")
            rc = 1
        else:
            print(msg)
    else:
        print(f"OK: installed __version__ == {version}")

    return rc


if __name__ == "__main__":
    sys.exit(main())
