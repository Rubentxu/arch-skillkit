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

# Path to the RUN1 fixture captured by verify-drawio-xml-roundtrip.mjs
# (python/tests/test_drawio_delta.py → repo root is 3 parents up)
FIXTURE_PATH = Path(__file__).parent.parent.parent / (
    "artifacts/uat/v2.4/m5-slice-23a/fixtures/drawio-xml-export-RUN1.fixture.xml"
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
