#!/usr/bin/env python3
"""Keep version.json's skill_version in sync with python/pyproject.toml.

Decision D-2 (docs/v2/46): pyproject.toml is the single source of version
truth; version.json is generated. Run with --check in gates to fail when
they drift:

    python3 scripts/release/sync-versions.py --check
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = ROOT / "python" / "pyproject.toml"
VERSION_JSON = ROOT / "skills" / "architecture-discovery" / "version.json"


def declared_version() -> str:
    text = PYPROJECT.read_text()
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
    if match is None:
        raise SystemExit(f"error: no version= found in {PYPROJECT}")
    return match.group(1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="fail instead of fixing when out of sync")
    args = parser.parse_args()

    version = declared_version()
    data = json.loads(VERSION_JSON.read_text())
    current = data.get("skill_version")

    if current == version:
        print(f"OK: skill_version == pyproject version ({version})")
        return 0
    if args.check:
        print(f"ERROR: skill_version {current!r} != pyproject version "
              f"{version!r}; run scripts/release/sync-versions.py")
        return 1
    data["skill_version"] = version
    VERSION_JSON.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"synced skill_version -> {version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
