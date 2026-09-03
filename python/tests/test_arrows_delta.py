"""V2.4 M5 slice 27 — arrows_delta classifier tests.

Unit tests for the pure classify_arrows function in arrows_delta.py.
Mirrors the drawio_delta test structure.
"""

from __future__ import annotations

import pytest

from archskillkit.projections.arrows_delta import (
    ARROWS_EMBED_ORIGIN,
    MalformedArrowsGraph,
    NonEmbedOrigin,
    classify_arrows,
)

# ---------- Bridge graph builders ---------------------------------------------


def _bridge_graph(nodes=None, rels=None):
    """Build a minimal bridge-shaped graph dict."""
    return {"nodes": nodes or [], "rels": rels or []}


def _node(cid, caption, labels=None, properties=None, position=None):
    """One bridge node."""
    return {
        "id": cid,
        "caption": caption,
        "position": position or {"x": 0.0, "y": 0.0},
        "labels": labels or [],
        "properties": properties or {},
        "style": None,
    }


def _rel(rid, rel_type, from_id, to_id, properties=None):
    """One bridge relation."""
    return {
        "id": rid,
        "type": rel_type,
        "fromId": from_id,
        "toId": to_id,
        "properties": properties or {},
        "style": None,
    }


# ---------- Arrows artifact builders ------------------------------------------


def _arrows_artifact(nodes=None, relationships=None):
    """Build a minimal arrows-v1 artifact (base artifact format)."""
    return {
        "schema": "arch-skillkit/arrows-v1",
        "nodes": nodes or [],
        "relationships": relationships or [],
    }


def _arrow_node(nid, name, labels=None):
    """One arrows-v1 node."""
    return {
        "id": nid,
        "labels": labels or [],
        "properties": {"name": name},
    }


def _arrow_rel(rid, rel_type, start, end):
    """One arrows-v1 relationship."""
    return {"id": rid, "type": rel_type, "start": start, "end": end, "properties": {}}


ORIGIN = ARROWS_EMBED_ORIGIN


class TestClassifyArrows:
    """Unit tests for classify_arrows."""

    def test_wrong_origin_rejected(self):
        """Non-embed origin raises NonEmbedOrigin."""
        base = _arrows_artifact()
        graph = _bridge_graph()
        with pytest.raises(NonEmbedOrigin):
            classify_arrows(
                str(base).encode(), graph, "https://evil.example"
            )

    def test_malformed_base_json_rejected(self):
        """Invalid base artifact JSON raises MalformedArrowsGraph."""
        graph = _bridge_graph([_node("n0", "A")])
        with pytest.raises(MalformedArrowsGraph):
            classify_arrows(b"<not-json>", graph, ORIGIN)

    def test_malformed_submitted_graph_rejected(self):
        """Non-object submitted graph raises MalformedArrowsGraph."""
        import json

        base = _arrows_artifact([_arrow_node("n0", "A")])
        with pytest.raises(MalformedArrowsGraph):
            classify_arrows(
                json.dumps(base).encode(), "not-an-object", ORIGIN
            )

    def test_no_change_is_zero_delta(self):
        """Identical base and submitted graphs yield zero deltas.

        The submitted graph must use the same positions as arrows_to_bridge
        produces (deterministic grid: col*240, row*120).
        """
        import json

        base = _arrows_artifact(
            [_arrow_node("n0", "Alpha"), _arrow_node("n1", "Beta")],
            [_arrow_rel("r0", "calls", "n0", "n1")],
        )
        # Use same positions as arrows_to_bridge produces for index 0 and 1
        graph = _bridge_graph(
            [_node("n0", "Alpha", position={"x": 0.0, "y": 0.0}),
             _node("n1", "Beta", position={"x": 240.0, "y": 0.0})],
            [_rel("r0", "calls", "n0", "n1")],
        )
        delta = classify_arrows(json.dumps(base).encode(), graph, ORIGIN)
        assert delta.semantic_changes == 0
        assert delta.presentation_changes == 0
        assert delta.semantic_candidates == []
        assert delta.unsupported == []

    def test_element_added(self):
        """A new node in submitted graph yields element_added."""
        import json

        base = _arrows_artifact([_arrow_node("n0", "Alpha")])
        graph = _bridge_graph(
            [_node("n0", "Alpha"), _node("n1", "Beta")]
        )
        delta = classify_arrows(json.dumps(base).encode(), graph, ORIGIN)
        assert delta.semantic_changes == 1
        cand = delta.semantic_candidates[0]
        assert cand.kind == "element_added"
        assert cand.name == "Beta"

    def test_element_removed(self):
        """A node removed from submitted graph yields element_removed."""
        import json

        base = _arrows_artifact(
            [_arrow_node("n0", "Alpha"), _arrow_node("n1", "Beta")]
        )
        graph = _bridge_graph([_node("n0", "Alpha")])
        delta = classify_arrows(json.dumps(base).encode(), graph, ORIGIN)
        assert delta.semantic_changes == 1
        cand = delta.semantic_candidates[0]
        assert cand.kind == "element_removed"
        assert cand.name == "Beta"

    def test_rename_is_remove_plus_add(self):
        """Renaming an element surfaces as element_removed + element_added."""
        import json

        base = _arrows_artifact([_arrow_node("n0", "Alpha")])
        graph = _bridge_graph([_node("n0", "Beta")])
        delta = classify_arrows(json.dumps(base).encode(), graph, ORIGIN)
        kinds = sorted(c.kind for c in delta.semantic_candidates)
        assert kinds == ["element_added", "element_removed"]

    def test_relation_added(self):
        """A new relation yields relation_added."""
        import json

        base = _arrows_artifact(
            [_arrow_node("n0", "Alpha"), _arrow_node("n1", "Beta")]
        )
        graph = _bridge_graph(
            [_node("n0", "Alpha"), _node("n1", "Beta")],
            [_rel("r0", "calls", "n0", "n1")],
        )
        delta = classify_arrows(json.dumps(base).encode(), graph, ORIGIN)
        assert delta.semantic_changes == 1
        cand = delta.semantic_candidates[0]
        assert cand.kind == "relation_added"
        assert cand.name == "calls"
        assert cand.target == "Beta"

    def test_relation_removed(self):
        """A removed relation yields relation_removed."""
        import json

        base = _arrows_artifact(
            [_arrow_node("n0", "Alpha"), _arrow_node("n1", "Beta")],
            [_arrow_rel("r0", "calls", "n0", "n1")],
        )
        graph = _bridge_graph([_node("n0", "Alpha"), _node("n1", "Beta")])
        delta = classify_arrows(json.dumps(base).encode(), graph, ORIGIN)
        assert delta.semantic_changes == 1
        cand = delta.semantic_candidates[0]
        assert cand.kind == "relation_removed"
        assert cand.name == "calls"

    def test_relation_type_change_is_remove_plus_add(self):
        """Changing a relation's type surfaces as relation_removed + relation_added."""
        import json

        base = _arrows_artifact(
            [_arrow_node("n0", "Alpha"), _arrow_node("n1", "Beta")],
            [_arrow_rel("r0", "calls", "n0", "n1")],
        )
        graph = _bridge_graph(
            [_node("n0", "Alpha"), _node("n1", "Beta")],
            [_rel("r0", "exposes", "n0", "n1")],
        )
        delta = classify_arrows(json.dumps(base).encode(), graph, ORIGIN)
        kinds = sorted(c.kind for c in delta.semantic_candidates)
        assert kinds == ["relation_added", "relation_removed"]

    def test_presentation_only_position_change(self):
        """Only position change yields zero semantic changes."""
        import json

        base = _arrows_artifact([_arrow_node("n0", "Alpha")])
        graph = _bridge_graph(
            [{"id": "n0", "caption": "Alpha", "position": {"x": 100.0, "y": 200.0}, "labels": [], "properties": {}, "style": None}]
        )
        delta = classify_arrows(json.dumps(base).encode(), graph, ORIGIN)
        assert delta.semantic_changes == 0
        assert delta.presentation_changes >= 1

    def test_presentation_only_properties_change(self):
        """Only properties change yields zero semantic changes."""
        import json

        base = _arrows_artifact([_arrow_node("n0", "Alpha")])
        graph = _bridge_graph(
            [{"id": "n0", "caption": "Alpha", "position": {"x": 0.0, "y": 0.0}, "labels": [], "properties": {"extra": "value"}, "style": None}]
        )
        delta = classify_arrows(json.dumps(base).encode(), graph, ORIGIN)
        assert delta.semantic_changes == 0
        assert delta.presentation_changes >= 1

    def test_no_caption_unsupported(self):
        """Node without caption yields NO_CAPTION unsupported code."""
        import json

        base = _arrows_artifact([_arrow_node("n0", "Alpha")])
        graph = _bridge_graph(
            [_node("n0", "Alpha"), {"id": "n1", "position": {"x": 0, "y": 0}, "labels": [], "properties": {}}]
        )
        delta = classify_arrows(json.dumps(base).encode(), graph, ORIGIN)
        unsupported_codes = [u.reason for u in delta.unsupported]
        assert "NO_CAPTION" in unsupported_codes

    def test_duplicate_caption_unsupported(self):
        """Two nodes with same caption yields DUPLICATE_IDENTITY unsupported code."""
        import json

        base = _arrows_artifact([_arrow_node("n0", "Alpha")])
        graph = _bridge_graph(
            [_node("n0", "Alpha"), _node("n1", "Alpha")]
        )
        delta = classify_arrows(json.dumps(base).encode(), graph, ORIGIN)
        unsupported_codes = [u.reason for u in delta.unsupported]
        assert "DUPLICATE_IDENTITY" in unsupported_codes

    def test_unresolved_relation_endpoint_unsupported(self):
        """Relation referencing unknown caption yields UNRESOLVED_RELATION_ENDPOINT."""
        import json

        base = _arrows_artifact([_arrow_node("n0", "Alpha")])
        graph = _bridge_graph(
            [_node("n0", "Alpha")],
            [_rel("r0", "calls", "n0", "n999")],
        )
        delta = classify_arrows(json.dumps(base).encode(), graph, ORIGIN)
        unsupported_codes = [u.reason for u in delta.unsupported]
        assert "UNRESOLVED_RELATION_ENDPOINT" in unsupported_codes

    def test_deterministic_output(self):
        """Two calls with same inputs yield identical output."""
        import json

        base = _arrows_artifact([_arrow_node("n0", "Alpha")])
        graph = _bridge_graph([_node("n0", "Alpha"), _node("n1", "Beta")])
        d1 = classify_arrows(json.dumps(base).encode(), graph, ORIGIN)
        d2 = classify_arrows(json.dumps(base).encode(), graph, ORIGIN)
        assert d1.model_dump() == d2.model_dump()

    def test_module_is_pure(self):
        """The classifier module must not import I/O, world or http."""
        import pathlib

        import archskillkit.projections.arrows_delta as mod

        src = pathlib.Path(mod.__file__).read_text(encoding="utf-8")
        for banned in (
            "import http",
            "urllib",
            "requests",
            "from archskillkit.world",
            "pathlib",
            "open(",
        ):
            assert banned not in src, f"impure import/call: {banned}"
        # hashlib is allowed for sha256
        assert "hashlib" in src
