"""ArchitectureSnapshot + ActionSuggestion (V2.4 M0 Slice 1).

Contracts: design/schemas/v2.4/{architecture-snapshot,action-suggestion}.yaml
M0 gate: snapshot reproducible for the same event log/generation; digest
changes when any revision changes; PID/runtime state stays out.
"""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest
import yaml
from jsonschema import validate as js_validate
from pydantic import ValidationError

from archskillkit.application import (
    ActionSuggestion,
    build_snapshot,
    snapshot_digest,
)
from archskillkit.world import ArchitectureWorld

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "design" / "schemas" / "v2.4"


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args],
                   check=True, capture_output=True)


@pytest.fixture()
def sandbox(monkeypatch, tmp_path):
    data = tmp_path / "data"
    monkeypatch.setenv("XDG_DATA_HOME", str(data))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    return data


@pytest.fixture()
def repo(tmp_path):
    """Fixture repo with one real commit (snapshot needs a HEAD)."""
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
def world(sandbox, repo):
    world = ArchitectureWorld.for_repo(repo).open()
    world.ensure_project()
    yield world
    world.close()


class TestSnapshotReproducibility:
    def test_same_state_same_digest_and_id(self, world):
        s1 = build_snapshot(world)
        s2 = build_snapshot(world)
        assert s1.canonical_json() == s2.canonical_json()
        assert s1.digest() == s2.digest()
        assert s1.snapshot_id == s2.snapshot_id

    def test_snapshot_id_derives_from_content_digest(self, world):
        snap = build_snapshot(world)
        assert snap.snapshot_id == f"snap-{snap.digest()[:16]}"

    def test_digest_excludes_snapshot_id(self, world):
        snap = build_snapshot(world)
        renamed = snap.model_copy(update={"snapshot_id": "snap-other"})
        assert snapshot_digest(renamed) == snap.digest()

    def test_canonical_json_is_sorted_and_compact(self, world):
        raw = build_snapshot(world).canonical_json()
        assert raw == json.dumps(json.loads(raw), sort_keys=True,
                                 separators=(",", ":"))


class TestSnapshotTracksRevisions:
    def test_world_change_changes_digest_and_event(self, world):
        before = build_snapshot(world)
        world.add_architecture_element("Orders API", "container")
        after = build_snapshot(world)
        assert after.digest() != before.digest()
        assert after.world_revision.event_id \
            != before.world_revision.event_id
        assert after.knowledge.elements == before.knowledge.elements + 1

    def test_policy_revision_tracks_rules(self, world):
        assert build_snapshot(world).policy_revision == "none"
        world.policies.record_rule(
            "no-ui-to-domain", "UI must not import domain",
            forbidden_relation="imports",
            source_category="ui", target_category="domain")
        with_rule = build_snapshot(world)
        assert with_rule.policy_revision != "none"
        assert with_rule.policy_revision == build_snapshot(world).policy_revision

    def test_git_commit_and_dirty_digest(self, world, repo):
        snap = build_snapshot(world)
        head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                              capture_output=True, text=True,
                              check=True).stdout.strip()
        assert snap.project_revision.git_commit == head
        assert snap.project_revision.dirty_digest is None

        (repo / "scratch.txt").write_text("dirty\n")
        dirty = build_snapshot(world)
        porcelain = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain"],
            capture_output=True, text=True, check=True).stdout
        assert dirty.project_revision.dirty_digest == hashlib.sha256(
            porcelain.encode()).hexdigest()

    def test_code_generation_none_without_index(self, world):
        assert build_snapshot(world).code_revision.generation == "none"

    def test_codeindex_current_generation_none_when_fresh(self, world):
        from archskillkit.codeindex import CodeIndex
        index = CodeIndex(world.workspace / "code.sqlite").open()
        try:
            assert index.current_generation is None
        finally:
            index.close()


class TestSnapshotContract:
    def test_matches_design_schema(self, world):
        schema = yaml.safe_load(
            (SCHEMA_DIR / "architecture-snapshot.yaml").read_text())
        js_validate(build_snapshot(world).model_dump(), schema)

    def test_no_runtime_state_in_payload_or_event_log(self, world):
        payload = json.loads(build_snapshot(world).canonical_json())
        blob = json.dumps(payload)
        assert "pid" not in blob
        assert "runtime" not in blob
        assert not any(e.type.startswith("runtime")
                       for e in world.graph.events)


class TestActionSuggestion:
    def test_round_trip(self):
        s = ActionSuggestion(
            action_id="act-1", reason_code="world.stale",
            parameters={"element": "Orders API"},
            preconditions=["world is open"],
            mutation_scope="workspace", risk="low",
            expected_effects=["refresh index"])
        assert s.model_dump()["mutation_scope"] == "workspace"
        assert ActionSuggestion(**s.model_dump()) == s

    def test_minimal_required_only(self):
        s = ActionSuggestion(action_id="act-2", reason_code="r",
                             mutation_scope="none", risk="low")
        assert s.parameters == {}
        assert s.preconditions == []

    def test_rejects_unknown_mutation_scope(self):
        with pytest.raises(ValidationError):
            ActionSuggestion(action_id="a", reason_code="r",
                             mutation_scope="database", risk="low")

    def test_rejects_extra_fields(self):
        with pytest.raises(ValidationError):
            ActionSuggestion(action_id="a", reason_code="r",
                             mutation_scope="none", risk="low",
                             execute=True)
