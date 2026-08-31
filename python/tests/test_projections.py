"""V2.2 Phase P0 — projection foundation.

VisualIntent schema (docs/v2/26), ProjectionAdapter contract
(docs/v2/27 + design/projections/*.yaml) and projection metadata
(design/schemas/projection-metadata.yaml + lifecycle in docs/v2/35).
Routing must be deterministic per the intent preference table; no
application-specific library may be imported here (UAT-P18).
"""

import pytest
from pydantic import ValidationError

from archskillkit.projections import (
    IntentType,
    ProjectionContext,
    ProjectionMetadata,
    ProjectionResult,
    ProjectionRouter,
    VisualIntent,
)
from archskillkit.projections.contract import ProjectionAdapter


class RecordingAdapter:
    """Smallest possible adapter: proves the contract without a renderer."""

    def __init__(self, name: str, intents: set[str], version: str = "0.1.0"):
        self.name = name
        self.supported_intents = frozenset(intents)
        self.version = version
        self.received: list[VisualIntent] = []

    def project(self, intent: VisualIntent, context: ProjectionContext) -> ProjectionResult:
        self.received.append(intent)
        return ProjectionResult(
            format=self.name,
            path=f"exports/projections/{intent.subject}.{self.name}",
            source_snapshot={
                "architecture_run": context.architecture_run,
                "code_index_revision": context.code_index_revision,
            },
            metrics={"nodes": 3, "edges": 2},
        )


@pytest.fixture()
def context():
    return ProjectionContext(
        project_id="fixture-b470c680",
        architecture_run="world",
        code_index_revision="",
        evidence_refs=[],
    )


@pytest.fixture()
def router():
    return ProjectionRouter(
        [
            RecordingAdapter("likec4", {"architecture"}),
            RecordingAdapter("arrows", {"exploration", "investigation", "knowledge_map"}),
            RecordingAdapter("drawio", {"technical_diagram", "proposal_board"}),
            RecordingAdapter("jsoncanvas", {"knowledge_map", "proposal_board", "investigation"}),
            RecordingAdapter("graphml", {"dependency_graph", "large_graph_analysis"}),
        ]
    )


class TestVisualIntent:
    def test_minimal_intent_defaults(self):
        intent = VisualIntent(type="knowledge_map", subject="orders")
        assert intent.audience == "engineer"
        assert intent.interaction == "exploratory"
        assert intent.detail == "medium"
        assert intent.editable is False
        assert intent.include_evidence is False
        assert intent.scope.depth is None

    def test_full_intent_like_design_example(self):
        intent = VisualIntent(
            type="dependency_graph", subject="orders", scope={"depth": 3},
            audience="engineer", interaction="exploratory", detail="medium",
        )
        assert intent.scope.depth == 3

    def test_unknown_type_rejected(self):
        with pytest.raises(ValidationError):
            VisualIntent(type="powerpoint", subject="orders")

    def test_intent_types_cover_spec(self):
        # docs/v2/26-visual-intent-spec.md "Tipos iniciales"
        assert set(IntentType.__args__) == {  # type: ignore[attr-defined]
            "architecture", "exploration", "technical_diagram", "knowledge_map",
            "dependency_graph", "large_graph_analysis", "proposal_board",
            "investigation",
        }


class TestProjectionContract:
    def test_adapter_protocol_satisfied(self):
        adapter = RecordingAdapter("jsoncanvas", {"knowledge_map"})
        assert isinstance(adapter, ProjectionAdapter)

    def test_result_carries_source_snapshot(self, router, context):
        adapter = router.route(VisualIntent(type="knowledge_map", subject="billing"))
        result = adapter.project(
            VisualIntent(type="knowledge_map", subject="billing"), context)
        # invariant 3 (docs/v2/27): projection must carry source snapshot
        assert result.source_snapshot["architecture_run"] == "world"
        assert result.warnings == []
        assert result.metrics.nodes == 3


class TestDeterministicRouting:
    @pytest.mark.parametrize("intent_type,expected", [
        ("architecture", "likec4"),
        ("exploration", "arrows"),
        ("technical_diagram", "drawio"),
        ("knowledge_map", "jsoncanvas"),
        ("dependency_graph", "graphml"),
        ("large_graph_analysis", "graphml"),
        ("proposal_board", "jsoncanvas"),
        ("investigation", "jsoncanvas"),
    ])
    def test_preference_table(self, router, intent_type, expected):
        adapter = router.route(VisualIntent(type=intent_type, subject="s"))
        assert adapter.name == expected

    def test_user_override_forces_format(self, router):
        # UAT-P11: the user can force another *compatible* projection —
        # an override may not escape the adapter's supported intents.
        adapter = router.route(
            VisualIntent(type="knowledge_map", subject="s"), force="arrows")
        assert adapter.name == "arrows"

    def test_incompatible_override_fails(self, router):
        with pytest.raises(ProjectionRouter.RoutingError):
            router.route(VisualIntent(type="knowledge_map", subject="s"),
                         force="likec4")

    def test_unknown_format_fails_cleanly(self, router):
        with pytest.raises(ProjectionRouter.RoutingError):
            router.route(VisualIntent(type="knowledge_map", subject="s"),
                         force="powerpoint")

    def test_adapter_must_support_routed_intent(self):
        router = ProjectionRouter([RecordingAdapter("likec4", {"architecture"})])
        with pytest.raises(ProjectionRouter.RoutingError):
            router.route(VisualIntent(type="knowledge_map", subject="s"))


class TestProjectionMetadata:
    def test_defaults_follow_design_schema(self):
        meta = ProjectionMetadata(
            projection_id="billing-jsoncanvas-1",
            projection_type="jsoncanvas",
            visual_intent="knowledge_map",
            source={"project_id": "fixture-b470c680",
                    "architecture_run": "world", "code_index_revision": ""},
            adapter_version="0.1.0",
            artifact_path="exports/projections/billing.canvas",
        )
        assert meta.status == "generated"
        assert meta.manually_modified is False
        assert meta.stale is False

    def test_lifecycle_states(self):
        assert ProjectionMetadata.ALLOWED_STATUSES == (
            "requested", "generated", "validated", "opened",
            "manually_modified", "stale", "superseded",
        )

    def test_invalid_status_rejected(self):
        with pytest.raises(ValidationError):
            ProjectionMetadata(
                projection_id="x", projection_type="jsoncanvas",
                visual_intent="knowledge_map",
                source={"project_id": "p", "architecture_run": "w",
                        "code_index_revision": ""},
                adapter_version="0.1.0",
                artifact_path="a.canvas",
                status="deleted",
            )

    def test_marking_stale_and_manual_edit(self):
        meta = ProjectionMetadata(
            projection_id="x", projection_type="jsoncanvas",
            visual_intent="knowledge_map",
            source={"project_id": "p", "architecture_run": "w",
                    "code_index_revision": ""},
            adapter_version="0.1.0", artifact_path="a.canvas",
        )
        stale = meta.model_copy(update={"stale": True})
        manual = meta.model_copy(update={"manually_modified": True,
                                         "status": "manually_modified"})
        assert stale.stale and meta.stale is False
        assert manual.status == "manually_modified"
