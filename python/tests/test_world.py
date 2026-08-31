"""Architecture World persistence + replay (M2-A3, H2-1, UAT2-004/018).

The ArchitectureWorld service encapsulates ActiveGraph behind the domain
(ADR-0024). Everything below runs against sandboxed XDG roots.
"""

import subprocess
from pathlib import Path

import pytest

from archskillkit.ids import compute_project_id
from archskillkit.packs.arch_core import ClaimData, EvidenceData, ObservationData
from archskillkit.world import ArchitectureWorld


@pytest.fixture()
def sandbox(monkeypatch, tmp_path):
    data = tmp_path / "data"
    monkeypatch.setenv("XDG_DATA_HOME", str(data))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    return data


@pytest.fixture()
def repo(tmp_path):
    repo = tmp_path / "fixture"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "main.rs").write_text("fn main() {}\n")
    _git(repo, "init", "-q")
    _git(repo, "remote", "add", "origin", "https://github.com/rubentxu/fixture.git")
    return repo


def observation(subject="domain.orders", predicate="exposes", obj="POST /orders"):
    return ObservationData(
        subject=subject, predicate=predicate, object=obj,
        evidence=EvidenceData(tool="semgrep", rule="spring.endpoint",
                              file="src/Orders.kt", start_line=10, end_line=18),
    )


class TestWorkspaceLayout:
    def test_layout_created_and_project_id_parity(self, sandbox, repo):
        world = ArchitectureWorld.for_repo(repo)
        world.open()
        pid = compute_project_id(str(repo.resolve()),
                                 "github.com/rubentxu/fixture")
        ws = sandbox / "arch-skillkit" / "projects" / pid
        assert ws.is_dir()
        assert (ws / "activegraph.sqlite").is_file()
        for sub in ("evidence", "knowledge", "likec4", "arrows", "reports", "exports"):
            assert (ws / sub).is_dir(), sub

    def test_repo_untouched_after_session(self, sandbox, repo):
        before = _git_out(repo, "status", "--porcelain")
        world = ArchitectureWorld.for_repo(repo)
        world.open()
        world.record_observation(observation())
        world.close()
        assert _git_out(repo, "status", "--porcelain") == before


class TestWorldState:
    def test_record_observation_evidence_claim(self, sandbox, repo):
        world = ArchitectureWorld.for_repo(repo)
        world.open()
        obs_id = world.record_observation(observation())
        ev_id = world.record_evidence(EvidenceData(
            tool="ast-grep", rule="rust-struct", file="src/main.rs"))
        claim_id = world.propose_claim(ClaimData(
            statement="orders is a bounded context", subjects=["orders"]))
        world.link_evidenced_by(claim_id, ev_id)

        snap = world.snapshot()
        assert snap["counts"]["observation"] == 1
        assert snap["counts"]["evidence"] == 1
        assert snap["counts"]["claim"] == 1
        assert snap["objects"][obs_id]["data"]["subject"] == "domain.orders"
        assert (claim_id, ev_id) in [
            (r["source"], r["target"]) for r in snap["relations"]
        ]
        world.close()

    def test_ensure_project_idempotent(self, sandbox, repo):
        world = ArchitectureWorld.for_repo(repo)
        world.open()
        world.ensure_project()
        world.ensure_project()
        world.close()
        world2 = ArchitectureWorld.for_repo(repo)
        world2.open()
        assert world2.snapshot()["counts"]["project"] == 1
        world2.close()


class TestReplayAndIsolation:
    def test_replay_reproduces_state(self, sandbox, repo):
        world = ArchitectureWorld.for_repo(repo)
        world.open()
        world.ensure_project()
        world.record_observation(observation())
        world.record_observation(observation(subject="infra.http"))
        report = world.replay_verify()
        assert report.ok, report.detail
        assert report.objects == 3  # project + 2 observations
        world.close()

    def test_fresh_instance_reads_replayed_state(self, sandbox, repo):
        world = ArchitectureWorld.for_repo(repo)
        world.open()
        world.record_observation(observation())
        world.close()

        world2 = ArchitectureWorld.for_repo(repo)
        world2.open()
        # nothing was written in this session: state comes from the log
        assert world2.snapshot()["counts"]["observation"] == 1
        world2.close()

    def test_project_isolation(self, sandbox, tmp_path):
        repo_a = tmp_path / "alpha"
        repo_b = tmp_path / "beta"
        for name, remote in (("alpha", "https://github.com/org/alpha.git"),
                             ("beta", "https://github.com/org/beta.git")):
            r = tmp_path / name
            r.mkdir()
            _git(r, "init", "-q")
            _git(r, "remote", "add", "origin", remote)

        wa = ArchitectureWorld.for_repo(tmp_path / "alpha")
        wa.open()
        wa.record_observation(observation(subject="alpha.thing"))
        wa.close()

        wb = ArchitectureWorld.for_repo(tmp_path / "beta")
        wb.open()
        wb.record_observation(observation(subject="beta.thing"))
        wb.close()

        assert wa.project_id != wb.project_id
        assert (wa.db_path).exists() and (wb.db_path).exists()
        assert wa.db_path != wb.db_path

        wb2 = ArchitectureWorld.for_repo(tmp_path / "beta")
        wb2.open()
        subjects = [o["data"]["subject"] for o in wb2.snapshot()["objects"].values()
                    if o["type"] == "observation"]
        assert subjects == ["beta.thing"]  # no cross-project bleed


def _git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


def _git_out(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args],
                          check=True, capture_output=True, text=True).stdout
