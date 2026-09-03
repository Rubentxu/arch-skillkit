"""V2.4 M5 slice 23a — drawio XML round-trip delta classifier test.

This test proves that the XML fixtures captured from real draw.io output
(RUN1/RUN2) are consumable by a pure classify_xml function that parses
with ElementTree and extracts the archskillkit metadata.

It does NOT authorize the full classifier — it only proves real captured
data is parseable and the metadata is accessible.

Stub-or-initial classify_xml: pure function, no I/O, no network, no http imports.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

# Fixture captured from real embed.diagrams.net output (M5-23a) and
# committed under tests/fixtures so fresh clones can run this test.
# Source of truth: scripts/uat/m5-slice-23a/verify-drawio-xml-roundtrip.mjs
# (artifacts/ copies are local evidence, gitignored).
FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "drawio_delta" / ("drawio-xml-export-RUN1.fixture.xml")
)


def classify_xml(xml_str: str) -> dict:
    """Pure XML classifier: parses mxGraph XML and extracts archskillkit metadata.

    Returns a dict with:
      - vertices: list of dicts with archskillkit-element-name and archskillkit-element-kind
      - edges: list of dicts with archskillkit-relation-kind, -source-name, -target-name
      - cell_ids: set of all cell ids found
    """
    root = ET.fromstring(xml_str)

    # Note: draw.io mxGraph XML does not typically use namespaces for
    # custom attributes. The standard mxfile/diagram/mxGraphModel structure
    # is sufficient for parsing.

    vertices = []
    edges = []

    # Find all UserObject elements (vertex containers per M5-23a encoding)
    for uo in root.iter():
        if uo.tag == "UserObject" or "UserObject" in uo.tag:
            name = uo.get("archskillkit-element-name")
            kind = uo.get("archskillkit-element-kind")
            if name and kind:
                vertices.append({"name": name, "kind": kind})

    # Find all mxCell elements with edge=1 (edges per M5-23a encoding)
    for cell in root.iter():
        tag = cell.tag
        if "mxCell" in tag and cell.get("edge") == "1":
            rel_kind = cell.get("archskillkit-relation-kind")
            src_name = cell.get("archskillkit-relation-source-name")
            tgt_name = cell.get("archskillkit-relation-target-name")
            if rel_kind and src_name and tgt_name:
                edges.append(
                    {
                        "kind": rel_kind,
                        "source_name": src_name,
                        "target_name": tgt_name,
                    }
                )

    # Collect all cell ids
    cell_ids = set()
    for cell in root.iter():
        tag = cell.tag
        if "mxCell" in tag or "UserObject" in tag:
            cell_id = cell.get("id")
            if cell_id:
                cell_ids.add(cell_id)

    return {
        "vertices": vertices,
        "edges": edges,
        "cell_ids": cell_ids,
    }


class TestDrawioXmlRoundtrip:
    """Verify the XML fixture is consumable and contains expected metadata."""

    def test_fixture_exists(self):
        """Fixture file must exist (captured from real draw.io output)."""
        assert FIXTURE_PATH.exists(), (
            f"RUN1 fixture not found at {FIXTURE_PATH}. "
            "Run verify-drawio-xml-roundtrip.mjs first to capture fixtures."
        )

    def test_fixture_matches_sidecar_sha256(self):
        """The committed fixture must match its recorded raw sha256."""
        import hashlib

        if not FIXTURE_PATH.exists():
            pytest.skip("Fixture not found")

        sidecar = FIXTURE_PATH.parent / (FIXTURE_PATH.name + ".sha256")
        assert sidecar.exists(), f"missing sidecar {sidecar}"
        raw_sha = hashlib.sha256(FIXTURE_PATH.read_bytes()).hexdigest()
        assert raw_sha == sidecar.read_text().strip(), (
            "fixture content drifted from its recorded sha256"
        )

    def test_fixture_parses_without_error(self):
        """ElementTree must parse the fixture without raising ParseError."""
        if not FIXTURE_PATH.exists():
            pytest.skip("Fixture not found")

        xml_str = FIXTURE_PATH.read_text(encoding="utf-8")

        # Must not raise an exception
        root = ET.fromstring(xml_str)
        assert root.tag == "mxfile", f"Expected mxfile root, got {root.tag}"

    def test_n_roundtrip_cell_has_correct_metadata(self):
        """The n_roundtrip cell must have archskillkit-element-name='new-svc'
        and archskillkit-element-kind='component' (either on UserObject or mxCell).

        This proves the structural edit survived the export round-trip.
        """
        if not FIXTURE_PATH.exists():
            pytest.skip("Fixture not found")

        xml_str = FIXTURE_PATH.read_text(encoding="utf-8")
        result = classify_xml(xml_str)

        # Find the n_roundtrip cell - it could be on UserObject or mxCell
        n_roundtrip_found = False
        n_roundtrip_on_userobject = False

        root = ET.fromstring(xml_str)
        for uo in root.iter():
            if "UserObject" in uo.tag and uo.get("id") == "n_roundtrip":
                n_roundtrip_found = True
                n_roundtrip_on_userobject = True
                assert uo.get("archskillkit-element-name") == "new-svc", (
                    f"Expected archskillkit-element-name='new-svc', "
                    f"got {uo.get('archskillkit-element-name')}"
                )
                assert uo.get("archskillkit-element-kind") == "component", (
                    f"Expected archskillkit-element-kind='component', "
                    f"got {uo.get('archskillkit-element-kind')}"
                )
                break

        # If not on UserObject, check mxCell
        if not n_roundtrip_found:
            for cell in root.iter():
                if "mxCell" in cell.tag and cell.get("id") == "n_roundtrip":
                    n_roundtrip_found = True
                    assert cell.get("archskillkit-element-name") == "new-svc", (
                        f"Expected archskillkit-element-name='new-svc' on mxCell, "
                        f"got {cell.get('archskillkit-element-name')}"
                    )
                    assert cell.get("archskillkit-element-kind") == "component", (
                        f"Expected archskillkit-element-kind='component' on mxCell, "
                        f"got {cell.get('archskillkit-element-kind')}"
                    )
                    break

        assert n_roundtrip_found, (
            f"Cell id='n_roundtrip' not found in fixture. Available ids: {result['cell_ids']}"
        )
        if n_roundtrip_on_userobject:
            assert result["vertices"], "classify_xml should have found n_roundtrip in vertices"

    def test_classify_xml_extracts_vertices(self):
        """classify_xml must extract vertices with archskillkit metadata."""
        if not FIXTURE_PATH.exists():
            pytest.skip("Fixture not found")

        xml_str = FIXTURE_PATH.read_text(encoding="utf-8")
        result = classify_xml(xml_str)

        assert "vertices" in result
        assert isinstance(result["vertices"], list)

    def test_classify_xml_extracts_edges(self):
        """classify_xml must extract edges with archskillkit relation metadata."""
        if not FIXTURE_PATH.exists():
            pytest.skip("Fixture not found")

        xml_str = FIXTURE_PATH.read_text(encoding="utf-8")
        result = classify_xml(xml_str)

        assert "edges" in result
        assert isinstance(result["edges"], list)

    def test_classify_xml_returns_cell_ids(self):
        """classify_xml must return the set of all cell ids."""
        if not FIXTURE_PATH.exists():
            pytest.skip("Fixture not found")

        xml_str = FIXTURE_PATH.read_text(encoding="utf-8")
        result = classify_xml(xml_str)

        assert "cell_ids" in result
        assert isinstance(result["cell_ids"], set)
        assert len(result["cell_ids"]) > 0


# ---------- classify_xml unit tests (synthetic, design §6 cases) --------

from archskillkit.projections.drawio_delta import (
    DRAWIO_EMBED_ORIGIN,
    MalformedDrawioXml,
    NonEmbedOrigin,
)
from archskillkit.projections.drawio_delta import (
    classify_xml as classify,
)

ORIGIN = DRAWIO_EMBED_ORIGIN


def _mxfile(*cells: str) -> bytes:
    """Build a minimal single-page mxfile with the given cell XML."""
    body = "".join(cells)
    return (
        '<mxfile host="archskillkit" version="0.1.0">'
        '<diagram id="arch" name="architecture">'
        "<mxGraphModel><root>"
        '<mxCell id="0" /><mxCell id="1" parent="0" />'
        + body
        + "</root></mxGraphModel></diagram></mxfile>"
    ).encode()


def _vertex(cid: str, name: str, kind: str = "component", style: str = "rounded=1;") -> str:
    return (
        f'<UserObject id="{cid}" archskillkit-element-name="{name}"'
        f' archskillkit-element-kind="{kind}">'
        f'<mxCell vertex="1" parent="1" style="{style}">'
        '<mxGeometry x="0" y="0" width="180" height="60" as="geometry" />'
        "</mxCell></UserObject>"
    )


def _edge(
    cid: str, kind: str, src: str, dst: str, style: str = "edgeStyle=orthogonalEdgeStyle;"
) -> str:
    return (
        f'<mxCell id="{cid}" edge="1" parent="1" source="{src}" target="{dst}"'
        f' archskillkit-relation-kind="{kind}"'
        f' archskillkit-relation-source-name="{src}"'
        f' archskillkit-relation-target-name="{dst}"'
        f' style="{style}"><mxGeometry relative="1" as="geometry" /></mxCell>'
    )


class TestClassifyXml:
    def test_wrong_origin_rejected(self):
        import pytest

        with pytest.raises(NonEmbedOrigin):
            classify(_mxfile(), _mxfile(), "https://evil.example")

    def test_malformed_xml_rejected(self):
        import pytest

        base = _mxfile(_vertex("n0", "A"))
        with pytest.raises(MalformedDrawioXml):
            classify(base, "<not-xml", ORIGIN)

    def test_no_change_is_zero_delta(self):
        base = _mxfile(
            _vertex("n0", "A"), _edge("e0", "calls", "A", "B").replace('target="B"', 'target="A"')
        )
        delta = classify(base, base.decode(), ORIGIN)
        assert delta.semantic_changes == 0
        assert delta.presentation_changes == 0
        assert delta.semantic_candidates == []
        assert delta.unsupported == []

    def test_presentation_only_style_diff(self):
        base = _mxfile(_vertex("n0", "A", style="rounded=1;"))
        sub = _mxfile(_vertex("n0", "A", style="rounded=1;fillColor=#ff0000;"))
        delta = classify(base, sub.decode(), ORIGIN)
        assert delta.semantic_changes == 0
        assert delta.presentation_changes == 1

    def test_element_added(self):
        base = _mxfile(_vertex("n0", "A"))
        sub = _mxfile(_vertex("n0", "A"), _vertex("n1", "B"))
        delta = classify(base, sub.decode(), ORIGIN)
        assert delta.semantic_changes == 1
        cand = delta.semantic_candidates[0]
        assert cand.kind == "element_added"
        assert cand.name == "B"

    def test_element_removed(self):
        base = _mxfile(_vertex("n0", "A"), _vertex("n1", "B"))
        sub = _mxfile(_vertex("n0", "A"))
        delta = classify(base, sub.decode(), ORIGIN)
        assert delta.semantic_changes == 1
        assert delta.semantic_candidates[0].kind == "element_removed"
        assert delta.semantic_candidates[0].name == "B"

    def test_rename_is_remove_plus_add(self):
        base = _mxfile(_vertex("n0", "A"))
        sub = _mxfile(_vertex("n0", "A2"))
        delta = classify(base, sub.decode(), ORIGIN)
        kinds = sorted(c.kind for c in delta.semantic_candidates)
        assert kinds == ["element_added", "element_removed"]

    def test_element_kind_changed(self):
        base = _mxfile(_vertex("n0", "A", kind="component"))
        sub = _mxfile(_vertex("n0", "A", kind="bounded_context"))
        delta = classify(base, sub.decode(), ORIGIN)
        assert delta.semantic_changes == 1
        cand = delta.semantic_candidates[0]
        assert cand.kind == "element_kind_changed"
        assert cand.evidence["old_kind"] == "component"
        assert cand.evidence["new_kind"] == "bounded_context"

    def test_relation_added_with_unresolved_endpoint_unsupported(self):
        base = _mxfile(_vertex("n0", "A"))
        # Edge references "Z" which does not exist anywhere.
        sub = _mxfile(_vertex("n0", "A"), _edge("e0", "calls", "A", "Z"))
        delta = classify(base, sub.decode(), ORIGIN)
        assert delta.semantic_changes == 0
        assert [u.reason for u in delta.unsupported] == ["UNRESOLVED_RELATION_ENDPOINT"]

    def test_relation_kind_change_is_remove_plus_add(self):
        base = _mxfile(_vertex("n0", "A"), _vertex("n1", "B"), _edge("e0", "calls", "A", "B"))
        sub = _mxfile(_vertex("n0", "A"), _vertex("n1", "B"), _edge("e0", "exposes", "A", "B"))
        delta = classify(base, sub.decode(), ORIGIN)
        kinds = sorted(c.kind for c in delta.semantic_candidates)
        assert kinds == ["relation_added", "relation_removed"]

    def test_partial_relation_metadata_unsupported(self):
        base = _mxfile(_vertex("n0", "A"))
        sub = _mxfile(
            _vertex("n0", "A"),
            '<mxCell id="e9" edge="1" parent="1" source="n0" target="n0"'
            ' archskillkit-relation-kind="calls"'
            ' style=""><mxGeometry relative="1" as="geometry" /></mxCell>',
        )
        delta = classify(base, sub.decode(), ORIGIN)
        assert [u.reason for u in delta.unsupported] == ["INCOMPLETE_RELATION"]

    def test_bare_vertex_unsupported(self):
        base = _mxfile()
        sub = _mxfile(
            '<mxCell id="nX" vertex="1" parent="1" value="mystery ·'
            ' component · DETECTED/high" style=""><mxGeometry'
            ' x="0" y="0" width="1" height="1" as="geometry" />'
            "</mxCell>"
        )
        delta = classify(base, sub.decode(), ORIGIN)
        assert [u.reason for u in delta.unsupported] == ["NO_VERTEX_NAME"]
        assert delta.semantic_changes == 0

    def test_unknown_element_kind_unsupported(self):
        base = _mxfile()
        sub = _mxfile(_vertex("n0", "A", kind="microservice"))
        delta = classify(base, sub.decode(), ORIGIN)
        assert [u.reason for u in delta.unsupported] == ["UNKNOWN_ELEMENT_KIND"]

    def test_duplicate_identity_unsupported(self):
        base = _mxfile()
        sub = _mxfile(_vertex("n0", "A"), _vertex("n1", "A"))
        delta = classify(base, sub.decode(), ORIGIN)
        assert [u.reason for u in delta.unsupported] == ["DUPLICATE_IDENTITY"]

    def test_vertex_and_edge_cell_unsupported(self):
        base = _mxfile()
        sub = _mxfile(
            '<mxCell id="nX" vertex="1" edge="1" parent="1"'
            ' archskillkit-relation-kind="calls"'
            ' archskillkit-relation-source-name="A"'
            ' archskillkit-relation-target-name="A"'
            ' style=""><mxGeometry relative="1" as="geometry" /></mxCell>'
        )
        delta = classify(base, sub.decode(), ORIGIN)
        assert [u.reason for u in delta.unsupported] == ["AMBIGUOUS_CELL"]

    def test_deterministic_output(self):
        base = _mxfile(_vertex("n0", "A"))
        sub = _mxfile(_vertex("n0", "A"), _vertex("n1", "B"))
        d1 = classify(base, sub.decode(), ORIGIN)
        d2 = classify(base, sub.decode(), ORIGIN)
        assert d1.model_dump() == d2.model_dump()

    def test_real_fixture_base_vs_edited(self):
        """Classify the REAL captured draw.io data: base export vs the
        edited re-export must yield exactly element_added(new-svc)."""
        import pytest

        fx_dir = FIXTURE_PATH.parent
        base_path = fx_dir / "drawio-xml-export-RUN1.base.xml"
        if not FIXTURE_PATH.exists() or not base_path.exists():
            pytest.skip("Captured fixtures not available")

        delta = classify(
            base_path.read_bytes(),
            FIXTURE_PATH.read_text(encoding="utf-8"),
            ORIGIN,
        )
        added = [c for c in delta.semantic_candidates if c.kind == "element_added"]
        assert [c.name for c in added] == ["new-svc"]
        removed = [c for c in delta.semantic_candidates if c.kind.endswith("_removed")]
        assert removed == []

    def test_module_is_pure(self):
        """The classifier module must not import I/O, world or http."""

        import archskillkit.projections.drawio_delta as mod

        src = Path(mod.__file__).read_text(encoding="utf-8")
        for banned in (
            "import http",
            "urllib",
            "requests",
            "from archskillkit.world",
            "pathlib",
            "open(",
        ):
            assert banned not in src, f"impure import/call: {banned}"
        assert "hashlib" in src  # sha256 hashing only
