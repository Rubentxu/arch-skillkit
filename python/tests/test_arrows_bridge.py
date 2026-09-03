"""Tests for arrows_bridge (V2.4 M5 slice 26).

Pure-function unit tests for the arrows-v1 → bridge shape mapper.
"""

from archskillkit.projections.arrows_bridge import (
    arrows_to_bridge,
    build_envelope,
    compute_sha256,
)


class TestArrowsToBridge:
    """Unit tests for arrows_to_bridge()."""

    def _doc(self, nodes, relationships):
        return {"nodes": nodes, "relationships": relationships}

    def test_empty_doc(self):
        doc = self._doc([], [])
        result = arrows_to_bridge(doc)
        assert result == {"nodes": [], "rels": []}

    def test_node_caption_from_name_property(self):
        doc = self._doc(
            [
                {
                    "id": "n1",
                    "labels": ["component"],
                    "properties": {"name": "Alpha", "origin": "DECLARED"},
                }
            ],
            [],
        )
        result = arrows_to_bridge(doc)
        assert len(result["nodes"]) == 1
        node = result["nodes"][0]
        assert node["id"] == "n1"
        assert node["caption"] == "Alpha"
        # name is not in properties
        assert "name" not in node["properties"]
        assert node["properties"].get("origin") == "DECLARED"

    def test_node_caption_falls_back_to_id(self):
        doc = self._doc(
            [{"id": "n1", "labels": ["component"], "properties": {"origin": "DECLARED"}}],
            [],
        )
        result = arrows_to_bridge(doc)
        assert result["nodes"][0]["caption"] == "n1"

    def test_node_position_deterministic_grid(self):
        doc = self._doc(
            [
                {"id": "n0", "labels": [], "properties": {}},
                {"id": "n1", "labels": [], "properties": {}},
                {"id": "n2", "labels": [], "properties": {}},
                {"id": "n3", "labels": [], "properties": {}},
                {"id": "n4", "labels": [], "properties": {}},
            ],
            [],
        )
        result = arrows_to_bridge(doc)
        # Grid: 4 cols, 240px wide, 120px tall
        assert result["nodes"][0]["position"] == {"x": 0.0, "y": 0.0}
        assert result["nodes"][1]["position"] == {"x": 240.0, "y": 0.0}
        assert result["nodes"][2]["position"] == {"x": 480.0, "y": 0.0}
        assert result["nodes"][3]["position"] == {"x": 720.0, "y": 0.0}
        assert result["nodes"][4]["position"] == {"x": 0.0, "y": 120.0}

    def test_rel_maps_start_end_to_fromId_toId(self):
        doc = self._doc(
            [
                {"id": "na", "labels": ["component"], "properties": {"name": "A"}},
                {"id": "nb", "labels": ["datastore"], "properties": {"name": "B"}},
            ],
            [
                {
                    "id": "r1",
                    "type": "calls",
                    "start": "na",
                    "end": "nb",
                    "properties": {"rule": "http"},
                },
            ],
        )
        result = arrows_to_bridge(doc)
        assert len(result["rels"]) == 1
        rel = result["rels"][0]
        assert rel["id"] == "r1"
        assert rel["fromId"] == "na"
        assert rel["toId"] == "nb"
        assert rel["type"] == "calls"

    def test_rel_skips_unresolved_endpoints(self):
        doc = self._doc(
            [{"id": "na", "labels": [], "properties": {}}],
            [
                {"id": "r1", "type": "calls", "start": "na", "end": "nb", "properties": {}},
            ],
        )
        result = arrows_to_bridge(doc)
        assert result["rels"] == []

    def test_style_is_null(self):
        doc = self._doc(
            [{"id": "n1", "labels": [], "properties": {}}],
            [],
        )
        result = arrows_to_bridge(doc)
        assert result["nodes"][0]["style"] is None
        assert result["rels"] == []


class TestComputeSha256:
    """Unit tests for compute_sha256()."""

    def test_stable_ordering(self):
        doc1 = {"nodes": [{"id": "a"}], "relationships": []}
        doc2 = {"relationships": [], "nodes": [{"id": "a"}]}
        # Same content, different key order → same SHA
        assert compute_sha256(doc1) == compute_sha256(doc2)

    def test_different_content_different_sha(self):
        doc1 = {"nodes": [{"id": "a"}], "relationships": []}
        doc2 = {"nodes": [{"id": "b"}], "relationships": []}
        assert compute_sha256(doc1) != compute_sha256(doc2)


class TestBuildEnvelope:
    """Unit tests for build_envelope()."""

    def _doc(self, nodes, relationships):
        return {"nodes": nodes, "relationships": relationships}

    def test_schema(self):
        doc = self._doc([], [])
        result = build_envelope(doc)
        assert result["schema"] == "arch-skillkit/arrows-artifact-v1"

    def test_doc_version(self):
        doc = self._doc([], [])
        result = build_envelope(doc)
        assert result["docVersion"] == 1

    def test_graph_shape(self):
        doc = self._doc(
            [{"id": "n1", "labels": ["component"], "properties": {"name": "Alpha"}}],
            [],
        )
        result = build_envelope(doc)
        assert "graph" in result
        assert "nodes" in result["graph"]
        assert "rels" in result["graph"]
        assert len(result["graph"]["nodes"]) == 1

    def test_sha256_present(self):
        doc = self._doc([], [])
        result = build_envelope(doc)
        assert "sha256" in result
        assert len(result["sha256"]) == 64  # SHA-256 hex

    def test_base_drift_false_when_no_generated_sha(self):
        doc = self._doc([], [])
        result = build_envelope(doc, generated_sha256=None)
        assert result["base_drift"] is False

    def test_base_drift_false_when_matches(self):
        doc = self._doc([], [])
        sha = compute_sha256(doc)
        result = build_envelope(doc, generated_sha256=sha)
        assert result["base_drift"] is False

    def test_base_drift_true_when_differs(self):
        doc = self._doc([], [])
        result = build_envelope(doc, generated_sha256="deadbeef" * 8)
        assert result["base_drift"] is True

    def test_generated_sha256_passed_through(self):
        doc = self._doc([], [])
        result = build_envelope(doc, generated_sha256="abc123")
        assert result["generated_sha256"] == "abc123"
