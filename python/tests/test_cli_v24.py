"""V2.4 CLI delivery-adapter commands: status / explain (slice 4).

The handlers must behave exactly like the application use cases: JSON
contracts from docs/v2/55 §4, stable error codes §10, exit codes 0/1.
"""

import json
import subprocess

import pytest

from archskillkit.cli import main
from archskillkit.packs.arch_core import ClaimData, EvidenceData, ObservationData
from archskillkit.world import ArchitectureWorld


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args],
                   check=True, capture_output=True)


@pytest.fixture()
def sandbox(monkeypatch, tmp_path):
    data = tmp_path / "data"
    monkeypatch.setenv("XDG_DATA_HOME", str(data))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "runtime"))
    return tmp_path


@pytest.fixture()
def repo(tmp_path):
    repo = tmp_path / "fixture"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "main.rs").write_text("fn main() {}\n")
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    _git(repo, "remote", "add", "origin",
         "https://github.com/rubentxu/fixture.git")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")
    return repo


@pytest.fixture()
def initialized(sandbox, repo, capsys):
    assert main(["init", "--repo", str(repo)]) == 0
    capsys.readouterr()  # drop init output
    return repo


def _json(capsys):
    out = capsys.readouterr().out
    return json.loads(out)


class TestStatusCommand:
    def test_fresh_project_suggests_discover(self, initialized, capsys):
        assert main(["status", "--repo", str(initialized)]) == 0
        payload = _json(capsys)
        assert payload["schema"] == "arch-skillkit/status-result-v1"
        assert payload["snapshot"]["snapshot_id"].startswith("snap-")
        reasons = {s["reason_code"] for s in payload["suggestions"]}
        assert {"INDEX_MISSING", "WORLD_EMPTY"} <= reasons
        action = payload["suggestions"][0]
        assert action["mutation_scope"] == "workspace"
        assert action["risk"] == "low"

    def test_status_reflects_world_content(self, initialized, capsys):
        with ArchitectureWorld.for_repo(initialized) as world:
            obs_id = world.record_observation(ObservationData(
                subject="orders-api", predicate="exposes",
                object="POST /orders",
                evidence=EvidenceData(tool="semgrep", rule="r",
                                      file="f.kt", start_line=1)))
            ev_id = world.record_evidence(EvidenceData(
                tool="ast-grep", rule="r2", file="g.kt", start_line=2))
            claim_id = world.propose_derived_claim(
                ClaimData(statement="orders-api exposes POST /orders",
                          subjects=["Orders API"], evidence_refs=[ev_id]),
                obs_id)
            world.accept_claim(claim_id)
            world.add_architecture_element("Orders API", "container")
        assert main(["status", "--repo", str(initialized)]) == 0
        payload = _json(capsys)
        reasons = {s["reason_code"] for s in payload["suggestions"]}
        assert "WORLD_EMPTY" not in reasons
        assert payload["snapshot"]["knowledge"]["elements"] == 1

    def test_status_without_world_fails_with_hint(self, sandbox, repo,
                                                  capsys):
        assert main(["status", "--repo", str(repo)]) == 1
        err = capsys.readouterr().err
        assert "no Architecture World" in err
        assert "init" in err


class TestExplainCommand:
    def test_explains_element_by_name(self, initialized, capsys):
        with ArchitectureWorld.for_repo(initialized) as world:
            world.record_observation(ObservationData(
                subject="orders-api", predicate="exposes",
                object="POST /orders",
                evidence=EvidenceData(tool="semgrep", rule="r",
                                      file="f.kt", start_line=1)))
            world.add_architecture_element("Orders API", "container")
        assert main(["explain", "--repo", str(initialized),
                     "Orders API"]) == 0
        payload = _json(capsys)
        assert payload["schema"] == "arch-skillkit/explanation-v1"
        assert payload["subject_type"] == "architecture_element"
        assert payload["gaps"] == ["element has no claim lineage recorded"]

    def test_explains_claim_lineage(self, initialized, capsys):
        with ArchitectureWorld.for_repo(initialized) as world:
            obs_id = world.record_observation(ObservationData(
                subject="orders-api", predicate="exposes",
                object="POST /orders",
                evidence=EvidenceData(tool="semgrep", rule="r",
                                      file="f.kt", start_line=1)))
            ev_id = world.record_evidence(EvidenceData(
                tool="ast-grep", rule="r2", file="g.kt", start_line=2))
            claim_id = world.propose_derived_claim(
                ClaimData(statement="orders-api exposes POST /orders",
                          subjects=["Orders API"], evidence_refs=[ev_id]),
                obs_id)
        assert main(["explain", "--repo", str(initialized),
                     claim_id]) == 0
        payload = _json(capsys)
        assert payload["subject_type"] == "claim"
        assert payload["observations"][0]["id"] == obs_id
        assert payload["evidence"][0]["id"] == ev_id
        assert payload["claims"][0]["status"] == "proposed"

    def test_unknown_subject_typed_error(self, initialized, capsys):
        assert main(["explain", "--repo", str(initialized),
                     "does-not-exist"]) == 1
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert payload["code"] == "SUBJECT_NOT_FOUND"
        assert "does-not-exist" in captured.err

    def test_explain_without_world_fails(self, sandbox, repo, capsys):
        assert main(["explain", "--repo", str(repo), "x"]) == 1
        assert "no Architecture World" in capsys.readouterr().err
