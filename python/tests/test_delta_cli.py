"""PR delta CLI (V2.4 M3, docs/v2/58, slice 11).

Gates: pure comparison (no live world); JSON round-trip preserves
state; same two state files always yield the same delta; markdown
emits added/removed/changed sections deterministically; CLI exit
codes 0/2 (0 success, 2 bad input).
"""

import json
import subprocess
import sys

from archskillkit.application.queries.delta import (
    SnapshotState,
    compute_delta_states,
)
from archskillkit.application.queries.delta_report import (
    render_delta_markdown,
)


def _state(elements=(), relations=(), unknowns=(),
           findings=(), rules=()):
    return SnapshotState(
        elements=tuple(elements),
        relations=frozenset(relations),
        unknowns=frozenset(unknowns),
        findings=tuple(findings),
        rules=tuple(rules),
    )


class TestSnapshotState:
    def test_json_round_trip(self):
        s = _state(
            elements=[("Orders", {"kind": "container", "confidence": "low"}),
                      ("Billing", {"kind": "component"})],
            relations=[("depends_on", "Orders", "Billing")],
            unknowns={"Orders"},
            findings=[{"severity": "low"}],
            rules=[{"name": "r1"}],
        )
        again = SnapshotState.from_json(s.to_json())
        assert s == again

    def test_to_json_has_schema(self):
        s = _state()
        data = json.loads(s.to_json())
        assert data["schema"] == "arch-skillkit/snapshot-state-v1"


class TestComputeDeltaStates:
    def test_pure_for_same_inputs(self):
        base = _state(elements=[("A", {"kind": "c"})])
        head = _state(elements=[("A", {"kind": "c"}), ("B", {"kind": "c"})])
        first = compute_delta_states(base, head)
        again = compute_delta_states(base, head)
        assert first.model_dump() == again.model_dump()

    def test_added_and_removed(self):
        base = _state(elements=[("A", {"kind": "c"}),
                                ("Legacy", {"kind": "c"})])
        head = _state(elements=[("A", {"kind": "c"}),
                                ("New", {"kind": "c"})])
        delta = compute_delta_states(base, head)
        assert delta.elements.added == ["New"]
        assert delta.elements.removed == ["Legacy"]
        assert delta.elements.changed == []

    def test_unknowns_move(self):
        base = _state(elements=[("A", {"kind": "c"})], unknowns={"A"})
        head = _state(elements=[("A", {"kind": "c"})], unknowns=set())
        delta = compute_delta_states(base, head)
        assert delta.unknowns == {"base": 1, "head": 0, "delta": -1}

    def test_relations_added_removed(self):
        base = _state(
            elements=[("A", {"kind": "c"}), ("B", {"kind": "c"})],
            relations=[("depends_on", "A", "B")])
        head = _state(
            elements=[("A", {"kind": "c"}), ("B", {"kind": "c"})],
            relations=[("exposes", "A", "B")])
        delta = compute_delta_states(base, head)
        assert delta.relations.added == ["A -[exposes]-> B"]
        assert delta.relations.removed == ["A -[depends_on]-> B"]


class TestDeltaMarkdown:
    def test_compact_when_empty(self):
        delta = compute_delta_states(_state(), _state())
        text = render_delta_markdown(delta)
        assert "No architecture changes detected." in text
        assert "Elements added" not in text

    def test_section_per_dimension(self):
        delta = compute_delta_states(
            _state(elements=[("Legacy", {})]),
            _state(elements=[("New", {})]))
        text = render_delta_markdown(delta)
        assert "## Elements added" in text
        assert "## Elements removed" in text
        assert "- `New`" in text
        assert "- `Legacy`" in text

    def test_deterministic(self):
        delta = compute_delta_states(
            _state(elements=[("Legacy", {})]),
            _state(elements=[("New", {})]))
        assert render_delta_markdown(delta) == render_delta_markdown(delta)


class TestDeltaCLI:
    def _state_path(self, tmp_path, name, state):
        path = tmp_path / name
        path.write_text(state.to_json())
        return path

    def test_cli_json_round_trip(self, tmp_path):
        base = _state(elements=[("A", {"kind": "c"})])
        head = _state(elements=[("A", {"kind": "c"}),
                                ("B", {"kind": "c"})])
        bp = self._state_path(tmp_path, "base.json", base)
        hp = self._state_path(tmp_path, "head.json", head)
        result = subprocess.run(
            [sys.executable, "-m", "archskillkit", "delta",
             "--base-state", str(bp), "--head-state", str(hp)],
            capture_output=True, text=True, check=False)
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        assert payload["elements"]["added"] == ["B"]

    def test_cli_markdown(self, tmp_path):
        base = _state(elements=[("Legacy", {})])
        head = _state(elements=[("New", {})])
        bp = self._state_path(tmp_path, "base.json", base)
        hp = self._state_path(tmp_path, "head.json", head)
        result = subprocess.run(
            [sys.executable, "-m", "archskillkit", "delta",
             "--base-state", str(bp), "--head-state", str(hp),
             "--format", "markdown", "--project", "demo"],
            capture_output=True, text=True, check=False)
        assert result.returncode == 0
        assert "# Architecture delta" in result.stdout
        assert "Project: `demo`" in result.stdout
        assert "- `New`" in result.stdout

    def test_cli_invalid_input_exits_2(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not-json")
        good = self._state_path(tmp_path, "good.json", _state())
        result = subprocess.run(
            [sys.executable, "-m", "archskillkit", "delta",
             "--base-state", str(bad), "--head-state", str(good)],
            capture_output=True, text=True, check=False)
        assert result.returncode == 2

    def test_cli_deterministic(self, tmp_path):
        base = _state(elements=[("Legacy", {})])
        head = _state(elements=[("New", {})])
        bp = self._state_path(tmp_path, "base.json", base)
        hp = self._state_path(tmp_path, "head.json", head)
        first = subprocess.run(
            [sys.executable, "-m", "archskillkit", "delta",
             "--base-state", str(bp), "--head-state", str(hp),
             "--format", "markdown"],
            capture_output=True, text=True, check=True)
        again = subprocess.run(
            [sys.executable, "-m", "archskillkit", "delta",
             "--base-state", str(bp), "--head-state", str(hp),
             "--format", "markdown"],
            capture_output=True, text=True, check=True)
        assert first.stdout == again.stdout
