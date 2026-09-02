"""Shared Phase C fixtures: a sandboxed repo whose Code Index is loaded
with the REAL Kotlin scanner payloads captured from the pinned V1
toolchain (see python/tests/fixtures/).

``build_kotlin_world`` is reusable from both pytest tests and the
standalone projection validation scripts (docs/v2/47 P7). The pytest
fixture is a thin wrapper around it that handles tmp_path cleanup.
"""
import subprocess
from pathlib import Path

from archskillkit.codeindex import CodeIndex
from archskillkit.world import ArchitectureWorld

FIXTURES = Path(__file__).parent / "fixtures"
KOTLIN_ROOT = FIXTURES  # virtual scan root the payloads are relative to

KOTLIN_RUN = "scan-1"


def load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


def build_kotlin_world(repo: Path):
    """Open Architecture World + Code Index on a sandboxed ``repo`` and
    ingest the Kotlin scan payloads. Caller owns ``repo`` and the
    returned ``(world, index)`` (must be closed when done).
    """
    import os

    os.environ.setdefault("XDG_DATA_HOME", str(repo.parent / "data"))
    os.environ.setdefault("XDG_STATE_HOME", str(repo.parent / "state"))
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "remote", "add", "origin",
         "https://github.com/rubentxu/kotlin-demo.git"],
        check=True,
    )
    world = ArchitectureWorld.for_repo(repo).open()
    world.ensure_project()
    index = CodeIndex(world.workspace / "code.sqlite").open()
    index.ingest_astgrep(load_fixture("astgrep-kotlin.json"),
                         scan_run_id=KOTLIN_RUN, scan_root=KOTLIN_ROOT)
    index.ingest_semgrep(load_fixture("semgrep-kotlin.json"),
                         scan_run_id=KOTLIN_RUN, scan_root=KOTLIN_ROOT)
    return world, index


import pytest


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    repo = tmp_path / "kotlin-demo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    return repo


@pytest.fixture()
def kotlin_world_index(repo):
    """Architecture World + Code Index with the real Kotlin scan ingested."""
    world, index = build_kotlin_world(repo)
    yield world, index
    index.close()
    world.close()