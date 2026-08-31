"""Shared Phase C fixtures: a sandboxed repo whose Code Index is loaded
with the REAL Kotlin scanner payloads captured from the pinned V1
toolchain (see python/tests/fixtures/)."""

import subprocess
from pathlib import Path

import pytest

from archskillkit.codeindex import CodeIndex
from archskillkit.world import ArchitectureWorld

FIXTURES = Path(__file__).parent / "fixtures"
KOTLIN_ROOT = FIXTURES  # virtual scan root the payloads are relative to

KOTLIN_RUN = "scan-1"


def load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    repo = tmp_path / "kotlin-demo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin",
                    "https://github.com/rubentxu/kotlin-demo.git"], check=True)
    return repo


@pytest.fixture()
def kotlin_world_index(repo):
    """Architecture World + Code Index with the real Kotlin scan ingested."""
    world = ArchitectureWorld.for_repo(repo).open()
    world.ensure_project()
    index = CodeIndex(world.workspace / "code.sqlite").open()
    index.ingest_astgrep(load_fixture("astgrep-kotlin.json"),
                         scan_run_id=KOTLIN_RUN, scan_root=KOTLIN_ROOT)
    index.ingest_semgrep(load_fixture("semgrep-kotlin.json"),
                         scan_run_id=KOTLIN_RUN, scan_root=KOTLIN_ROOT)
    yield world, index
    index.close()
    world.close()
