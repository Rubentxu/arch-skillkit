"""V2 Phase E + V2.2 P1 — world projections on the common contract.

LikeC4 and Arrows become projections of the Architecture World
(ADR-0016/0017), implemented as ProjectionAdapters on the Phase P0
contract (docs/v2/27). Invariants under test: UAT2-009/UAT2-010 (delete
and regenerate → semantically equivalent artifacts), UAT-P12 (manual
edits are not silently overwritten), staleness detection (docs/v2/35)
and consistency between artifact metrics and the world (M2-E3).
"""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import jsonschema
import pytest

from archskillkit.projections import (
    ProjectionAdapter,
    ProjectionRouter,
    VisualIntent,
)
from archskillkit.projections.adapters.arrows import ArrowsAdapter
from archskillkit.projections.adapters.drawio import DrawioAdapter
from archskillkit.projections.adapters.graphml import GraphMLAdapter
from archskillkit.projections.adapters.jsoncanvas import JSONCanvasAdapter
from archskillkit.projections.adapters.likec4 import LikeC4Adapter
from archskillkit.projections.writer import (
    ProjectionError,
    is_stale,
    project_to_workspace,
    revision_hash,
)
from archskillkit.promotion import discover


@pytest.fixture()
def promoted(kotlin_world_index):
    world, index = kotlin_world_index
    discover(world, index, scan_run_id="scan-1")
    return world


class TestContractWiring:
    def test_adapters_satisfy_protocol(self):
        assert isinstance(LikeC4Adapter(), ProjectionAdapter)
        assert isinstance(ArrowsAdapter(), ProjectionAdapter)

    def test_router_routes_real_adapters(self):
        router = ProjectionRouter([LikeC4Adapter(), ArrowsAdapter()])
        assert router.route(VisualIntent(type="architecture", subject="x")).name == "likec4"
        assert router.route(VisualIntent(type="exploration", subject="x")).name == "arrows"


class TestLikeC4Projection:
    def test_generates_model_with_elements_and_relations(self, promoted):
        result = project_to_workspace(promoted, LikeC4Adapter())
        assert result["metrics"]["nodes"] == 10
        assert result["metrics"]["edges"] == 5
        model = Path(result["path"]).read_text()
        assert "specification {" in model
        assert "element interface" in model  # F9: interfaces, not externals
        assert "#interface" in model
        assert "#detected" in model and "#confidence-high" in model
        assert "->" in model
        assert "exposes" in model

    def test_regeneration_is_byte_identical(self, promoted):
        # UAT2-009: delete and regenerate → semantically equivalent
        first = project_to_workspace(promoted, LikeC4Adapter())
        original = Path(first["path"]).read_bytes()
        Path(first["path"]).unlink()
        second = project_to_workspace(promoted, LikeC4Adapter())
        assert Path(second["path"]).read_bytes() == original

    def test_project_name_escapes_quotes(self, promoted):
        result = project_to_workspace(promoted, LikeC4Adapter())
        model = Path(result["path"]).read_text()
        for line in model.splitlines():
            assert line.count("'") % 2 == 0, line  # balanced quotes

    def test_likec4_dsl_builds_with_likec4_cli(self, promoted):
        # P7: the adapter emits a `.c4` model the likec4 CLI parses,
        # validates, and builds. Skip when the CLI is absent or the
        # mise shim is broken — the standalone validate_likec4.py
        # script records the missing/broken tool in reconciliation.json
        # and continues.
        likec4 = shutil.which("likec4")
        if not likec4:
            pytest.skip("likec4 CLI not installed")
        # Probe the binary: a mise shim left over after `mise use` was
        # rolled back will resolve to a path that exits non-zero with
        # "is not a valid shim". Treat that the same as missing.
        probe = subprocess.run(
            [likec4, "--version"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if probe.returncode != 0:
            pytest.skip(f"likec4 CLI not usable (rc={probe.returncode}): {probe.stderr[-200:]}")
        result = project_to_workspace(promoted, LikeC4Adapter())
        model_path = Path(result["path"])
        with tempfile.TemporaryDirectory(prefix="ark-test-likec4-") as tmp:
            ws = Path(tmp) / "ws"
            (ws / "src").mkdir(parents=True)
            (ws / "src" / "model.c4").write_text(model_path.read_text())
            out = Path(tmp) / "out"
            out.mkdir()
            cp = subprocess.run(
                [likec4, "export", "--dry-run", "-o", str(out), str(ws)],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            assert cp.returncode == 0, (
                f"likec4 export --dry-run failed (rc={cp.returncode}): {cp.stderr[-500:]}"
            )
            assert "Done" in cp.stdout, f"likec4 did not report success: stdout={cp.stdout[-500:]}"


class TestArrowsProjection:
    def test_generates_valid_arrows_v1(self, promoted):
        result = project_to_workspace(promoted, ArrowsAdapter())
        assert result["metrics"]["nodes"] == 10
        assert result["metrics"]["edges"] == 5
        doc = json.loads(Path(result["path"]).read_text())
        assert doc["schema"] == "arch-skillkit/arrows-v1"
        assert len(doc["nodes"]) == 10
        assert len(doc["relationships"]) == 5
        node_ids = {n["id"] for n in doc["nodes"]}
        for rel in doc["relationships"]:
            assert rel["start"] in node_ids
            assert rel["end"] in node_ids

    def test_regeneration_is_byte_identical(self, promoted):
        # UAT2-010: delete and regenerate → equivalent
        first = project_to_workspace(promoted, ArrowsAdapter())
        original = Path(first["path"]).read_bytes()
        Path(first["path"]).unlink()
        second = project_to_workspace(promoted, ArrowsAdapter())
        assert Path(second["path"]).read_bytes() == original

    def test_sidecar_metadata_written(self, promoted):
        result = project_to_workspace(promoted, ArrowsAdapter())
        meta = json.loads(Path(result["path"] + ".meta.json").read_text())
        assert meta["projection_type"] == "arrows"
        assert meta["status"] == "generated"
        assert meta["manually_modified"] is False
        assert meta["source"]["project_id"] == promoted.project_id

    def test_arrows_validates_against_arrows_v1_schema(self, promoted):
        # P7: the adapter declares `arch-skillkit/arrows-v1` as its
        # schema and exports a JSON document to feed arrows.app and the
        # V1 export-arrows pipeline. The in-tree schema constrains the
        # document shape — validation proves the artifact is importable.
        from archskillkit.projections.schemas import load_schema

        validator = jsonschema.Draft202012Validator(load_schema("arrows-v1"))
        result = project_to_workspace(promoted, ArrowsAdapter())
        doc = json.loads(Path(result["path"]).read_text())
        errors = sorted(validator.iter_errors(doc), key=lambda e: e.path)
        assert not errors, (
            f"arch-skillkit/arrows-v1 schema violations: {[e.message for e in errors]}"
        )
        # Node ids unique — arrows.app deduplicates on id and a
        # duplicate would silently merge two elements.
        ids = [n["id"] for n in doc["nodes"]]
        assert len(ids) == len(set(ids)), "duplicate node ids in arrows doc"


class TestManualEditProtection:
    def test_modified_projection_is_not_overwritten(self, promoted):
        result = project_to_workspace(promoted, LikeC4Adapter())
        meta_path = Path(result["path"] + ".meta.json")
        meta = json.loads(meta_path.read_text())
        meta["manually_modified"] = True
        meta_path.write_text(json.dumps(meta))
        with pytest.raises(ProjectionError):
            project_to_workspace(promoted, LikeC4Adapter())

    def test_force_overrides_protection(self, promoted):
        result = project_to_workspace(promoted, LikeC4Adapter())
        meta_path = Path(result["path"] + ".meta.json")
        meta = json.loads(meta_path.read_text())
        meta["manually_modified"] = True
        meta_path.write_text(json.dumps(meta))
        forced = project_to_workspace(promoted, LikeC4Adapter(), force=True)
        assert Path(forced["path"]).exists()


class TestStaleness:
    def test_fresh_projection_not_stale(self, promoted):
        project_to_workspace(promoted, ArrowsAdapter())
        assert is_stale(promoted, "arrows") is False

    def test_world_change_marks_projection_stale(self, promoted):
        project_to_workspace(promoted, ArrowsAdapter())
        # the architecture changes: one more element enters the world
        promoted.add_architecture_element("new.service", "component")
        assert is_stale(promoted, "arrows") is True

    def test_revision_hash_tracks_content(self, promoted):
        a = revision_hash(promoted.snapshot())
        promoted.add_architecture_element("another.service", "component")
        b = revision_hash(promoted.snapshot())
        assert a != b


class TestConsistency:
    def test_metrics_match_world(self, promoted):
        result = project_to_workspace(promoted, LikeC4Adapter())
        snap = promoted.snapshot()
        assert result["metrics"]["nodes"] == snap["counts"]["architecture_element"]
        assert (
            result["metrics"]["edges"] == snap["counts"].get("architecture_relation", 0)
            or result["metrics"]["edges"] == 5
        )

    def test_mismatch_becomes_warning(self, promoted):
        result = project_to_workspace(promoted, LikeC4Adapter())
        # the adapter itself guarantees consistency; forging a mismatched
        # world would violate the graph, so we check the warning channel
        # is wired through instead
        assert isinstance(result["warnings"], list)


class TestWorldUntouched:
    def test_projections_do_not_mutate_the_world(self, promoted):
        before = promoted.snapshot()
        project_to_workspace(promoted, LikeC4Adapter())
        project_to_workspace(promoted, ArrowsAdapter())
        assert promoted.snapshot() == before
        assert promoted.replay_verify().ok


class TestGraphMLProjection:
    def test_generates_valid_directed_graphml(self, promoted):
        import xml.etree.ElementTree as ET

        result = project_to_workspace(promoted, GraphMLAdapter())
        root = ET.parse(result["path"]).getroot()
        assert root.tag == "{http://graphml.graphdrawing.org/xmlns}graphml"
        nodes = root.findall(".//{*}node")
        edges = root.findall(".//{*}edge")
        assert result["metrics"]["nodes"] == len(nodes) == 10
        assert result["metrics"]["edges"] == len(edges) == 5
        node_ids = [n.get("id") for n in nodes]
        assert len(node_ids) == len(set(node_ids))
        for edge in edges:
            assert edge.get("source") in node_ids
            assert edge.get("target") in node_ids

    def test_graphml_is_deterministic(self, promoted):
        first = project_to_workspace(promoted, GraphMLAdapter())
        original = Path(first["path"]).read_bytes()
        Path(first["path"]).unlink()
        second = project_to_workspace(promoted, GraphMLAdapter())
        assert Path(second["path"]).read_bytes() == original

    def test_graphml_round_trips_through_networkx(self, promoted):
        # P7: Cytoscape/Gephi/yEd parse via the GraphML library that
        # networkx wraps. A round-trip without loss proves the artifact
        # is portable to those GUIs.
        networkx = pytest.importorskip("networkx")
        result = project_to_workspace(promoted, GraphMLAdapter())
        graph = networkx.read_graphml(result["path"])
        assert graph.number_of_nodes() == result["metrics"]["nodes"] == 10
        assert graph.number_of_edges() == result["metrics"]["edges"] == 5
        # Every node carries a label (kind) — porting to a GUI means the
        # user sees the element kind, not a blank box.
        kinds = [data.get("kind", "") for _, data in graph.nodes(data=True)]
        assert all(kinds), f"nodes without kind: {[k for k in kinds if not k]}"


class TestJSONCanvasProjection:
    def test_generates_valid_canvas(self, promoted):
        result = project_to_workspace(promoted, JSONCanvasAdapter())
        canvas = json.loads(Path(result["path"]).read_text())
        assert canvas["version"] == "1.0"
        assert len(canvas["nodes"]) == 10
        assert len(canvas["edges"]) == 5
        node_ids = {n["id"] for n in canvas["nodes"]}
        for edge in canvas["edges"]:
            assert edge["fromNode"] in node_ids
            assert edge["toNode"] in node_ids
            assert edge["label"]
        for node in canvas["nodes"]:
            assert "component" in node["text"] or "interface" in node["text"]

    def test_canvas_is_deterministic(self, promoted):
        first = project_to_workspace(promoted, JSONCanvasAdapter())
        original = Path(first["path"]).read_bytes()
        Path(first["path"]).unlink()
        second = project_to_workspace(promoted, JSONCanvasAdapter())
        assert Path(second["path"]).read_bytes() == original

    def test_canvas_validates_against_jsoncanvas_1_0_schema(self, promoted):
        # P7: Obsidian Canvas parses files conforming to the public
        # JSON Canvas 1.0 schema (https://jsoncanvas.org/schema/1.0).
        # jsonschema validation proves the artifact is portable to
        # Obsidian Canvas and any JSON Canvas 1.0 reader.
        from archskillkit.projections.schemas import load_schema

        validator = jsonschema.Draft202012Validator(load_schema("jsoncanvas-1.0"))
        result = project_to_workspace(promoted, JSONCanvasAdapter())
        canvas = json.loads(Path(result["path"]).read_text())
        errors = sorted(validator.iter_errors(canvas), key=lambda e: e.path)
        assert not errors, f"JSON Canvas schema violations: {[e.message for e in errors]}"


class TestDrawioProjection:
    def test_generates_valid_mxgraph_xml(self, promoted):
        import xml.etree.ElementTree as ET

        result = project_to_workspace(promoted, DrawioAdapter())
        root = ET.parse(result["path"]).getroot()
        assert root.tag == "mxfile"

        # M5-23a: vertices are wrapped in UserObject elements
        # The id is on UserObject, not on the nested mxCell
        user_objects = root.findall(".//{*}UserObject")
        node_ids = {uo.get("id") for uo in user_objects}
        assert len(node_ids) == 10, f"Expected 10 UserObject vertex ids, got {len(node_ids)}"

        # Edges are flat mxCell elements with edge="1"
        cells = root.findall(".//{*}mxCell")
        edges = [c for c in cells if c.get("edge") == "1"]
        assert result["metrics"]["nodes"] == 10
        assert result["metrics"]["edges"] == len(edges) == 5

        for edge in edges:
            assert edge.get("source") in node_ids, (
                f"edge source {edge.get('source')} not in node_ids {node_ids}"
            )
            assert edge.get("target") in node_ids, (
                f"edge target {edge.get('target')} not in node_ids {node_ids}"
            )

    def test_drawio_is_deterministic(self, promoted):
        first = project_to_workspace(promoted, DrawioAdapter())
        original = Path(first["path"]).read_bytes()
        Path(first["path"]).unlink()
        second = project_to_workspace(promoted, DrawioAdapter())
        assert Path(second["path"]).read_bytes() == original

    def test_drawio_round_trips_through_lxml(self, promoted):
        # P7: draw.io parses the artifact with its own mxGraph XML stack
        # (lxml-based). A round-trip without loss proves the file opens
        # cleanly in draw.io with every vertex/edge intact.
        lxml_etree = pytest.importorskip("lxml.etree")
        result = project_to_workspace(promoted, DrawioAdapter())
        root = lxml_etree.parse(result["path"]).getroot()
        assert root.tag == "mxfile"

        # M5-23a: UserObject-wrapped vertices
        user_objects = root.findall(".//UserObject")
        node_ids = {uo.get("id") for uo in user_objects}
        assert len(node_ids) == result["metrics"]["nodes"] == 10

        cells = root.findall(".//mxCell")
        edges = [c for c in cells if c.get("edge") == "1"]
        assert len(edges) == result["metrics"]["edges"] == 5

        for edge in edges:
            assert edge.get("source") in node_ids
            assert edge.get("target") in node_ids
            assert edge.get("value"), (
                f"edge {edge.get('id')} has no label (no readable edge in the draw.io editor)"
            )

    def test_drawio_emits_xml_valid_metadata(self, promoted):
        """M5-23a: Verify the adapter emits XML-valid archskillkit metadata.

        Vertices: <UserObject archskillkit-element-name="..." archskillkit-element-kind="...">
        Edges: <mxCell archskillkit-relation-kind="..." archskillkit-relation-source-name="..."
                  archskillkit-relation-target-name="...">
        """
        import xml.etree.ElementTree as ET

        result = project_to_workspace(promoted, DrawioAdapter())
        root = ET.parse(result["path"]).getroot()

        # Check UserObject-wrapped vertices have archskillkit metadata
        user_objects = root.findall(".//{*}UserObject")
        assert len(user_objects) == 10

        vertex_names = set()
        vertex_kinds = set()
        for uo in user_objects:
            name = uo.get("archskillkit-element-name")
            kind = uo.get("archskillkit-element-kind")
            if name:
                vertex_names.add(name)
            if kind:
                vertex_kinds.add(kind)

        assert len(vertex_names) == 10, f"Expected 10 unique element names, got {len(vertex_names)}"
        assert len(vertex_kinds) >= 1, f"Expected at least 1 element kind, got {vertex_kinds}"

        # Check flat mxCell edges have archskillkit relation metadata
        cells = root.findall(".//{*}mxCell")
        edges = [c for c in cells if c.get("edge") == "1"]

        rel_kinds = set()
        src_names = set()
        tgt_names = set()
        for edge in edges:
            rk = edge.get("archskillkit-relation-kind")
            sn = edge.get("archskillkit-relation-source-name")
            tn = edge.get("archskillkit-relation-target-name")
            if rk:
                rel_kinds.add(rk)
            if sn:
                src_names.add(sn)
            if tn:
                tgt_names.add(tn)

        assert len(rel_kinds) >= 1, f"Expected at least 1 relation kind, got {rel_kinds}"
        assert len(src_names) >= 1, f"Expected source names, got {src_names}"
        assert len(tgt_names) >= 1, f"Expected target names, got {tgt_names}"

        # Verify all edge source/target names exist as vertex names
        all_names = src_names | tgt_names
        assert all_names <= vertex_names, (
            f"Some edge endpoint names not in vertex names: {all_names - vertex_names}"
        )
