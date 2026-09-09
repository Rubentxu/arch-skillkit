"""T-3 regression tests: runtime installer atomicity + last-known-good.

The runtime installer MUST:

1. Apply shebang fixes in the staging directory BEFORE the atomic
   rename to `final`, so a crash never leaves a partially-mutated
   runtime active.
2. Preserve the previous install under `.previous-<version>-<platform>`
   when overwriting, providing a rollback anchor (last-known-good).
3. Clean up the staging directory on any failure.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def fix_shebangs():
    """Import the `_fix_venv_shebangs` helper once for the module."""
    sys.path.insert(0, str(ROOT / "python" / "src"))
    from archskillkit.runtime import _fix_venv_shebangs
    return _fix_venv_shebangs


def _build_staging_with_baked_shebang(
    parent: Path, version: str, key: str,
    runtime_root: Path,
) -> Path:
    """Create a staging dir with a semgrep binary whose shebang
    encodes the runtime_root path."""
    staging = parent / f"staging-{version}"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    bin_dir = staging / "semgrep-venv" / "bin"
    bin_dir.mkdir(parents=True)
    shebang = f"#!{runtime_root}/python\n".encode()
    bin_dir.joinpath("semgrep").write_bytes(shebang + b"import sys\nsys.exit(0)\n")
    bin_dir.joinpath("semgrep").chmod(0o755)
    return staging


def test_shebang_fix_rewrites_staging_before_replace(
    tmp_path: Path, fix_shebangs
):
    """After staging fix + atomic rename, `final` shebang points to
    the runtime install dir (not the staging dir)."""
    runtimes = tmp_path / "runtimes"
    runtimes.mkdir()
    version, key = "0.5.0", "linux/x86_64"
    runtime_root = runtimes / version / key
    # Build a staging dir with a baked shebang pointing at the
    # eventual runtime dir (the rename happens before consumers
    # run, so the shebang is OK after the rename).
    staging = _build_staging_with_baked_shebang(
        runtimes, version, key, runtime_root
    )
    final = runtime_root

    # NEW (T-3) protocol: fix shebangs on staging BEFORE rename.
    fix_shebangs(staging, staging)
    final.mkdir(parents=True)
    os.replace(staging, final)

    shebang = (final / "semgrep-venv" / "bin" / "semgrep").read_bytes().split(b"\n", 1)[0]
    # The shebang must reference the runtime install dir.
    assert str(runtime_root).encode() in shebang, shebang
    # The shebang must not reference the staging dir.
    assert str(staging).encode() not in shebang, shebang
    # The staging dir must be gone after the rename.
    assert not staging.exists()


def test_previous_install_preserved_on_overwrite(tmp_path: Path, fix_shebangs):
    """Reinstalling vX must leave the prior vX under .previous-<v>-<p>."""
    runtimes = tmp_path / "runtimes"
    runtimes.mkdir()
    version, key = "0.5.0", "linux/x86_64"
    previous = runtimes / f".previous-{version}-{key}"
    final = runtimes / version / key

    # 1st install: build staging, fix shebangs, rename to final.
    staging1 = _build_staging_with_baked_shebang(
        runtimes, version, key, runtimes / version / key
    )
    fix_shebangs(staging1, staging1)
    final.mkdir(parents=True)
    os.replace(staging1, final)
    (final / "sentinel.txt").write_text("first")

    # 2nd install: simulate a re-install of the same version. The
    # T-3 protocol moves the previous install aside as the rollback
    # anchor BEFORE the rename.
    staging2 = _build_staging_with_baked_shebang(
        runtimes, f"{version}-retry", key, runtimes / version / key
    )
    fix_shebangs(staging2, staging2)
    if previous.exists():
        shutil.rmtree(previous)
    shutil.move(str(final), str(previous))
    os.replace(staging2, final)

    assert previous.exists(), f"rollback anchor not at {previous}"
    assert (previous / "sentinel.txt").read_text() == "first"
    assert not staging2.exists()


def test_staging_cleaned_on_rename(tmp_path: Path, fix_shebangs):
    """After a successful rename, staging dir is gone."""
    runtimes = tmp_path / "runtimes"
    runtimes.mkdir()
    staging = _build_staging_with_baked_shebang(
        runtimes, "0.5.0", "linux/x86_64",
        runtimes / "0.5.0" / "linux/x86_64",
    )
    final = runtimes / "0.5.0" / "linux/x86_64"
    fix_shebangs(staging, staging)
    final.mkdir(parents=True)
    os.replace(staging, final)
    assert not staging.exists()


def test_fix_venv_shebangs_idempotent_on_final(
    tmp_path: Path, fix_shebangs
):
    """Calling the helper with the legacy signature
    `(runtime_dir, staging_path)` after a rename still rewrites a
    shebang that contains the staging path."""
    runtimes = tmp_path / "runtimes"
    runtimes.mkdir()
    final = runtimes / "0.5.0" / "linux/x86_64"
    final.mkdir(parents=True)

    staging_path = runtimes / "old-staging"
    staging_path.mkdir()
    bin_dir = final / "semgrep-venv" / "bin"
    bin_dir.mkdir(parents=True)
    # Shebang contains `staging_path` (a real semgrep-venv bakes the
    # path it was created at; before the fix that's the staging path).
    bin_dir.joinpath("semgrep").write_bytes(
        f"#!{staging_path}/python\nimport sys\n".encode()
    )
    fix_shebangs(final, staging_path)
    shebang = (final / "semgrep-venv" / "bin" / "semgrep").read_bytes().split(b"\n", 1)[0]
    assert str(staging_path).encode() not in shebang
    assert str(final).encode() in shebang
