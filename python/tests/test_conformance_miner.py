"""Conformance Miner tests (V2.4 M6 slice 30, docs/v2/59 §M6).

Tests the ``conformance_miner`` module and the ``POST /rule-candidate-record``
Control Plane endpoint.
"""

from __future__ import annotations

import json as _json
import subprocess
import sys

import pytest

from archskillkit.conformance_miner import mine
from archskillkit.world import ArchitectureWorld

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture()
def world(tmp_path, monkeypatch):
    """Empty world with no relations."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "runtime"))
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "main.rs").write_text("fn main() {}\n")
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "test")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")
    subprocess.run(
        [sys.executable, "-m", "archskillkit", "init", "--repo", str(repo)],
        check=True,
        capture_output=True,
    )
    w = ArchitectureWorld.for_repo(str(repo)).open()
    yield w
    w.close()


@pytest.fixture()
def world_with_patterns(world):
    """World with two element kinds and repeated relations forming patterns.

    Pattern A (above threshold): component -[depends_on]-> component (support=4)
    Pattern B (above threshold): interface -[exposes]-> interface (support=3)
    Pattern C (below threshold): component -[calls]-> interface (support=1)
    """
    # Add elements of two kinds
    c1 = world.add_architecture_element("ServiceA", "component")
    c2 = world.add_architecture_element("ServiceB", "component")
    c3 = world.add_architecture_element("ServiceC", "component")
    i1 = world.add_architecture_element("API", "interface")
    i2 = world.add_architecture_element("Port", "interface")

    # Pattern A: component -[depends_on]-> component (support=4)
    world.add_architecture_relation("depends_on", c1, c2)
    world.add_architecture_relation("depends_on", c2, c1)
    world.add_architecture_relation("depends_on", c1, c3)
    world.add_architecture_relation("depends_on", c3, c2)

    # Pattern B: interface -[exposes]-> interface (support=3)
    world.add_architecture_relation("exposes", i1, i2)
    world.add_architecture_relation("exposes", i2, i1)
    world.add_architecture_relation("exposes", i1, i1)

    # Pattern C: component -[calls]-> interface (support=1 — below threshold)
    world.add_architecture_relation("calls", c1, i1)

    yield world


# ---------------------------------------------------------------------------
# Module unit tests
# ---------------------------------------------------------------------------


class TestMine:
    def test_empty_world_returns_empty_list(self, world):
        candidates = mine(world, min_support=3)
        assert candidates == []

    def test_pattern_above_threshold(self, world_with_patterns):
        candidates = mine(world_with_patterns, min_support=3)
        assert len(candidates) == 2

    def test_pattern_below_threshold(self, world_with_patterns):
        # Pattern C has support=1, below default min_support=3
        candidates = mine(world_with_patterns, min_support=3)
        candidate_ids = [c.candidate_id for c in candidates]
        assert "calls-component-interface" not in candidate_ids

    def test_min_support_boundary(self, world_with_patterns):
        # At support=4, only Pattern A qualifies
        candidates = mine(world_with_patterns, min_support=4)
        assert len(candidates) == 1
        assert candidates[0].candidate_id == "depends_on-component-component"

    def test_min_support_one(self, world_with_patterns):
        candidates = mine(world_with_patterns, min_support=1)
        assert len(candidates) == 3  # A, B, C all qualify

    def test_candidate_fields(self, world_with_patterns):
        candidates = mine(world_with_patterns, min_support=3)
        candidates.sort(key=lambda c: c.candidate_id)
        # Pattern A
        ca = next(c for c in candidates if c.candidate_id == "depends_on-component-component")
        assert ca.rel_kind == "depends_on"
        assert ca.source_kind == "component"
        assert ca.target_kind == "component"
        assert ca.support == 4
        assert len(ca.example_relation_ids) == 4
        assert ca.status == "candidate"
        assert ca.proposed_rule.name == "depends_on-component-component-rule"
        assert ca.proposed_rule.forbidden_relation == "depends_on"
        assert ca.proposed_rule.source_category == "component"
        assert ca.proposed_rule.target_category == "component"
        assert ca.proposed_rule.severity == "medium"
        assert "DRAFT from observed pattern" in ca.proposed_rule.statement
        # Pattern B
        cb = next(c for c in candidates if c.candidate_id == "exposes-interface-interface")
        assert cb.rel_kind == "exposes"
        assert cb.support == 3

    def test_example_relation_ids_capped_at_five(self, world):
        # Create 7 relations of same pattern using valid "component" kind
        elements = [world.add_architecture_element(f"Service{i}", "component") for i in range(7)]
        for i in range(7):
            world.add_architecture_relation("calls", elements[i], elements[(i + 1) % 7])
        candidates = mine(world, min_support=3)
        assert len(candidates) == 1
        assert len(candidates[0].example_relation_ids) == 5  # capped

    def test_determinism_identical_json_twice(self, world_with_patterns):
        first = mine(world_with_patterns, min_support=3)
        second = mine(world_with_patterns, min_support=3)
        assert _json.dumps([c.model_dump() for c in first]) == _json.dumps(
            [c.model_dump() for c in second]
        )

    def test_candidate_id_determinism(self, world_with_patterns):
        """Same pattern always produces same candidate_id regardless of scan order."""
        candidates = mine(world_with_patterns, min_support=1)
        for c in candidates:
            expected = f"{c.rel_kind}-{c.source_kind}-{c.target_kind}"
            assert c.candidate_id == expected

    def test_no_mutation(self, world_with_patterns):
        """Mining does not change the world's relation count."""
        rel_count_before = len(world_with_patterns.architecture_relations())
        mine(world_with_patterns, min_support=3)
        rel_count_after = len(world_with_patterns.architecture_relations())
        assert rel_count_before == rel_count_after

    def test_sorted_by_candidate_id(self, world_with_patterns):
        candidates = mine(world_with_patterns, min_support=1)
        ids = [c.candidate_id for c in candidates]
        assert ids == sorted(ids)


# ---------------------------------------------------------------------------
# CLI adapter tests
# ---------------------------------------------------------------------------


def test_mine_conformance_cli_empty(sworld, capsys):
    """CLI returns empty candidates list for empty world."""
    import argparse

    from archskillkit.delivery.cli.mine_conformance import handle

    ns = argparse.Namespace(repo=str(sworld.root), min_support=3)
    rc = handle(ns, sworld)
    assert rc == 0
    out = capsys.readouterr().out
    envelope = _json.loads(out)
    assert envelope["schema"] == "arch-skillkit/conformance-mining-v1"
    assert envelope["candidates"] == []


def test_mine_conformance_cli_with_patterns(sworld_with_patterns, capsys):
    """CLI returns candidates above threshold."""
    import argparse

    from archskillkit.delivery.cli.mine_conformance import handle

    ns = argparse.Namespace(repo=str(sworld_with_patterns.root), min_support=3)
    rc = handle(ns, sworld_with_patterns)
    assert rc == 0
    out = capsys.readouterr().out
    envelope = _json.loads(out)
    assert len(envelope["candidates"]) == 2


# ---------------------------------------------------------------------------
# Control Plane endpoint tests
# ---------------------------------------------------------------------------


def _http_caller(start_env, repo_path):
    """Return a caller function for the given server start envelope."""
    import urllib.error
    import urllib.request

    def _call(path, method="GET", json_payload=None):
        url = start_env["url"] + path
        data = _json.dumps(json_payload).encode() if json_payload is not None else None
        req = urllib.request.Request(
            url,
            method=method,
            data=data,
            headers={
                "Authorization": f"Bearer {start_env['token']}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.status, _json.loads(resp.read())
        except urllib.error.HTTPError as e:
            return e.code, _json.loads(e.read())

    return _call


def test_rule_candidate_record_403_no_admin(server_no_admin):
    """Without --admin the endpoint returns 403 ADMIN_DISABLED."""
    call = _http_caller(server_no_admin["start"], server_no_admin["repo_path"])
    status, body = call(
        "/rule-candidate-record",
        method="POST",
        json_payload={
            "candidate_id": "calls-component-interface",
            "rel_kind": "calls",
            "source_kind": "component",
            "target_kind": "interface",
            "severity": "high",
            "approved_by": "alice",
        },
    )
    assert status == 403
    assert body["code"] == "ADMIN_DISABLED"


def test_rule_candidate_record_400_bad_severity(server_admin):
    """Invalid severity returns 400."""
    call = _http_caller(server_admin["start"], server_admin["repo_path"])
    status, body = call(
        "/rule-candidate-record",
        method="POST",
        json_payload={
            "candidate_id": "calls-component-interface",
            "rel_kind": "calls",
            "source_kind": "component",
            "target_kind": "interface",
            "severity": "critical",  # invalid
            "approved_by": "alice",
        },
    )
    assert status == 400
    assert "severity" in body["message"].lower()


def test_rule_candidate_record_400_missing_field(server_admin):
    """Missing field returns 400."""
    call = _http_caller(server_admin["start"], server_admin["repo_path"])
    status, _body = call(
        "/rule-candidate-record",
        method="POST",
        json_payload={
            "candidate_id": "calls-component-interface",
            "rel_kind": "calls",
            # missing source_kind
            "target_kind": "interface",
            "severity": "high",
            "approved_by": "alice",
        },
    )
    assert status == 400


def test_rule_candidate_record_400_extra_field(server_admin):
    """Extra field returns 400."""
    call = _http_caller(server_admin["start"], server_admin["repo_path"])
    status, _body = call(
        "/rule-candidate-record",
        method="POST",
        json_payload={
            "candidate_id": "calls-component-interface",
            "rel_kind": "calls",
            "source_kind": "component",
            "target_kind": "interface",
            "severity": "high",
            "approved_by": "alice",
            "extra": "forbidden",
        },
    )
    assert status == 400


def test_rule_candidate_record_400_empty_string(server_admin):
    """Empty string field returns 400."""
    call = _http_caller(server_admin["start"], server_admin["repo_path"])
    status, _body = call(
        "/rule-candidate-record",
        method="POST",
        json_payload={
            "candidate_id": "calls-component-interface",
            "rel_kind": "",
            "source_kind": "component",
            "target_kind": "interface",
            "severity": "high",
            "approved_by": "alice",
        },
    )
    assert status == 400


def test_rule_candidate_record_200_happy(server_admin):
    """Valid body records the rule and returns 200."""
    call = _http_caller(server_admin["start"], server_admin["repo_path"])
    status, body = call(
        "/rule-candidate-record",
        method="POST",
        json_payload={
            "candidate_id": "depends_on-component-component",
            "rel_kind": "depends_on",
            "source_kind": "component",
            "target_kind": "component",
            "severity": "high",
            "approved_by": "alice",
        },
    )
    assert status == 200
    assert body["rule_recorded"] is True
    assert body["rule_name"] == "depends_on-component-component-rule"

    # Verify the rule was actually recorded
    w = ArchitectureWorld.for_repo(server_admin["repo_path"]).open()
    try:
        rules = w.find_objects("architecture_rule")
        rule_names = [r["data"]["name"] for r in rules]
        assert "depends_on-component-component-rule" in rule_names
    finally:
        w.close()


def test_rule_candidate_record_409_duplicate(server_admin):
    """Recording the same rule twice returns 409 RULE_EXISTS."""
    call = _http_caller(server_admin["start"], server_admin["repo_path"])
    payload = {
        "candidate_id": "depends_on-component-component",
        "rel_kind": "depends_on",
        "source_kind": "component",
        "target_kind": "component",
        "severity": "high",
        "approved_by": "alice",
    }
    # First call succeeds
    status1, _ = call("/rule-candidate-record", method="POST", json_payload=payload)
    assert status1 == 200
    # Second call returns 409
    status2, body2 = call("/rule-candidate-record", method="POST", json_payload=payload)
    assert status2 == 409
    assert body2["error"]["code"] == "RULE_EXISTS"
    assert body2["rule_recorded"] is False


# ---------------------------------------------------------------------------
# Test fixtures for control plane
# ---------------------------------------------------------------------------


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    return tmp_path


@pytest.fixture()
def sworld(tmp_path, monkeypatch):
    """Simple world — no patterns, no relations."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "runtime"))
    repo = tmp_path / "sworld"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "main.rs").write_text("fn main() {}\n")
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "test")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")
    subprocess.run(
        [sys.executable, "-m", "archskillkit", "init", "--repo", str(repo)],
        check=True,
        capture_output=True,
    )
    w = ArchitectureWorld.for_repo(str(repo)).open()
    yield w
    w.close()


@pytest.fixture()
def sworld_with_patterns(sworld):
    """World with Pattern A (support=4) and Pattern B (support=3)."""
    c1 = sworld.add_architecture_element("ServiceA", "component")
    c2 = sworld.add_architecture_element("ServiceB", "component")
    c3 = sworld.add_architecture_element("ServiceC", "component")
    i1 = sworld.add_architecture_element("API", "interface")
    i2 = sworld.add_architecture_element("Port", "interface")

    # Pattern A: component -[depends_on]-> component (support=4)
    sworld.add_architecture_relation("depends_on", c1, c2)
    sworld.add_architecture_relation("depends_on", c2, c1)
    sworld.add_architecture_relation("depends_on", c1, c3)
    sworld.add_architecture_relation("depends_on", c3, c2)

    # Pattern B: interface -[exposes]-> interface (support=3)
    sworld.add_architecture_relation("exposes", i1, i2)
    sworld.add_architecture_relation("exposes", i2, i1)
    sworld.add_architecture_relation("exposes", i1, i1)

    yield sworld


@pytest.fixture()
def server_no_admin(sandbox, sworld):
    """Control plane server without admin."""
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "archskillkit",
            "control-plane",
            "--repo",
            str(sworld.root),
            "--port",
            "0",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    line = proc.stdout.readline()
    assert line.strip(), f"server died: {proc.stderr.read()}"
    start = _json.loads(line)
    yield {"start": start, "repo_path": str(sworld.root)}
    proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture()
def server_admin(sandbox, sworld):
    """Control plane server with admin enabled."""
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "archskillkit",
            "control-plane",
            "--repo",
            str(sworld.root),
            "--port",
            "0",
            "--admin",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    line = proc.stdout.readline()
    assert line.strip(), f"server died: {proc.stderr.read()}"
    start = _json.loads(line)
    yield {"start": start, "repo_path": str(sworld.root)}
    proc.terminate()
    proc.wait(timeout=10)
