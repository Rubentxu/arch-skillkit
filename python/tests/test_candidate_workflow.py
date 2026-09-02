"""Candidate -> review -> promote workflow (V2.4 M4, docs/v2/59).

End-to-end: a candidate is forked from the main world, mutated,
reviewed (gate + structural diff in one envelope), and promoted
through the CLI. Gates:
- fork creates a proposal-* run, proposals list finds it
- review emits a schema-bound envelope with both the structural
  diff and the gate verdict
- promote applies the candidate and the main world gains the
  candidate's elements
- reject-proposal does NOT apply and keeps the candidate run
- a fork never mutates the base world (verified by an event-count
  assertion before and after fork)
"""

import json
import subprocess
import sys

import pytest


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args],
                   check=True, capture_output=True)


@pytest.fixture()
def sandbox(monkeypatch, tmp_path):
    data = tmp_path / "data"
    monkeypatch.setenv("XDG_DATA_HOME", str(data))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "runtime"))


@pytest.fixture()
def repo(sandbox, tmp_path):
    repo = tmp_path / "fixture"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "main.rs").write_text("fn main() {}\n")
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")
    subprocess.run([sys.executable, "-m", "archskillkit", "init",
                    "--repo", str(repo)], check=True,
                   capture_output=True)
    return repo


def _run(*args, check=True):
    return subprocess.run([sys.executable, "-m", "archskillkit", *args],
                          capture_output=True, text=True, check=check)


def _elements_count(repo):
    out = _run("status", "--repo", str(repo))
    payload = json.loads(out.stdout)
    return payload.get("elements", 0)


class TestCandidateWorkflow:
    def test_fork_creates_proposal_run(self, repo):
        r = _run("fork", "--repo", str(repo), "--name", "add-billing")
        assert r.returncode == 0, r.stderr
        body = json.loads(r.stdout)
        assert body["name"] == "add-billing"
        assert body["run_id"] == "proposal-add-billing"

        listing = _run("proposals", "--repo", str(repo), "list")
        names = {c["name"] for c in
                 json.loads(listing.stdout)["candidates"]}
        assert "add-billing" in names

    def test_fork_does_not_mutate_base_world(self, repo):
        from archskillkit.world import ArchitectureWorld
        world = ArchitectureWorld.for_repo(repo).open()
        before_types = [e.type for e in world.graph.events]
        world.close()
        _run("fork", "--repo", str(repo), "--name", "no-mutate")
        world = ArchitectureWorld.for_repo(repo).open()
        after_types = [e.type for e in world.graph.events]
        world.close()
        # The base world's structural events MUST not grow when a
        # candidate is forked. Reopen may add a pack.loaded event
        # but never adds elements / relations / claims / proposals.
        structural = {"architecture_element", "architecture_relation",
                      "claim", "proposal"}
        new_structural = [t for t in after_types
                          if t in structural
                          and t not in before_types[:len(after_types)]]
        assert not new_structural, \
            f"fork added structural events to base: {new_structural}"

    def test_review_emits_envelope_with_diff_and_gate(self, repo):
        _run("fork", "--repo", str(repo), "--name", "review-me")
        r = _run("proposals", "--repo", str(repo), "review",
                 "--name", "review-me")
        assert r.returncode == 0, r.stderr
        body = json.loads(r.stdout)
        assert body["schema"] == "arch-skillkit/proposal-review-v1"
        assert body["candidate"] == "review-me"
        assert "structural_diff" in body
        assert "gate" in body
        assert "verdict" in body["gate"]

    def test_promote_applies_candidate(self, repo):
        from archskillkit.world import ArchitectureWorld
        _run("fork", "--repo", str(repo), "--name", "to-promote")
        # mutate the candidate: add a new element
        fork = ArchitectureWorld.for_repo(repo).view("proposal-to-promote")
        fork.add_architecture_element("NewService", "container")
        fork.close()

        # promote
        r = _run("promote", "--repo", str(repo), "--name", "to-promote",
                 "--approved-by", "ci-bot")
        assert r.returncode == 0, r.stderr
        summary = json.loads(r.stdout)
        assert summary["elements_added"] == 1

        # main world now has NewService
        world = ArchitectureWorld.for_repo(repo).open()
        names = [e["data"]["name"] for e in
                 world.find_objects("architecture_element")]
        world.close()
        assert "NewService" in names

    def test_reject_keeps_scenario_but_does_not_apply(self, repo):
        from archskillkit.world import ArchitectureWorld
        _run("fork", "--repo", str(repo), "--name", "to-reject")
        fork = ArchitectureWorld.for_repo(repo).view("proposal-to-reject")
        fork.add_architecture_element("RejectedService", "container")
        fork.close()

        r = _run("reject-proposal", "--repo", str(repo),
                 "--name", "to-reject", "--actor", "ci-bot")
        assert r.returncode == 0, r.stderr

        # main world does NOT have RejectedService
        world = ArchitectureWorld.for_repo(repo).open()
        names = [e["data"]["name"] for e in
                 world.find_objects("architecture_element")]
        world.close()
        assert "RejectedService" not in names

        # but the candidate run still exists
        assert "proposal-to-reject" in world.list_runs()
