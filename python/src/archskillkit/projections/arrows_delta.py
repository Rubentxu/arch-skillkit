"""Arrows ProjectionDelta classifier (V2.4 M5 slice 27).

Pure function module: parses the arrows-v1 artifact (base) and a
submitted bridge-shaped graph export, both normalized to the bridge
postMessage shape, and classifies every difference as presentation-only
or semantic. NO I/O, NO world access, NO http imports.

Bridge graph shape (arch-skillkit/arrows-artifact-v1):
  nodes: [{id, caption, position:{x,y}, labels, properties, style}]
  rels:  [{id, fromId, toId, type, properties, style}]

Identity rules:
  - Element: matched by caption (unique within a diagram)
  - Relation: matched by (type, fromCaption, toCaption)
    (fromId/toId in the export map back to captions via the node set)

Semantic changes:
  - element_added / element_removed
  - relation_added / relation_removed

Presentation-only (never semantic candidates):
  - position changes (docs/v2/54 §9: PresentationProfile out of scope)
  - labels / properties / style changes on matched identities

Unsupported codes:
  - NO_CAPTION: node without caption in submitted graph
  - DUPLICATE_IDENTITY: two nodes share the same caption
  - UNRESOLVED_RELATION_ENDPOINT: relation references a caption not in the
    submitted or base graph
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

DELTA_SCHEMA = "arch-skillkit/arrows-delta-v1"

# The only origin a submitted export may come from.
# Enforced here as defence in depth; the delivery layer also validates.
ARROWS_EMBED_ORIGIN = "same-origin"

SemanticKind = Literal[
    "element_added",
    "element_removed",
    "relation_added",
    "relation_removed",
]

# Stable reason codes for unsupported conditions.
R_NO_CAPTION = "NO_CAPTION"
R_DUPLICATE_IDENTITY = "DUPLICATE_IDENTITY"
R_UNRESOLVED_RELATION_ENDPOINT = "UNRESOLVED_RELATION_ENDPOINT"


class ArrowsDeltaError(ValueError):
    """Raised when the submitted payload cannot be classified at all."""

    code = "ARROWS_DELTA_ERROR"


class NonEmbedOrigin(ArrowsDeltaError):
    code = "NON_EMBED_ORIGIN"


class MalformedArrowsGraph(ArrowsDeltaError):
    code = "MALFORMED_GRAPH"


class SemanticCandidate(BaseModel):
    """One semantic change candidate."""

    model_config = ConfigDict(extra="forbid")

    kind: SemanticKind
    name: str
    target: str | None = None
    rel_kind: str | None = None
    confidence: Literal["high", "medium", "low"] = "high"
    evidence: dict[str, Any] = Field(default_factory=dict)


class UnsupportedChange(BaseModel):
    """One unsupported condition preventing classification."""

    model_config = ConfigDict(extra="forbid")

    node_id: str | None = None
    rel_id: str | None = None
    reason: str
    detail: str = ""


class ProjectionDelta(BaseModel):
    """Result of classifying the delta between base artifact and submitted graph."""

    model_config = ConfigDict(extra="forbid")

    schema: Literal["arch-skillkit/arrows-delta-v1"] = DELTA_SCHEMA  # type: ignore[assignment]
    presentation_changes: int
    semantic_changes: int
    semantic_candidates: list[SemanticCandidate] = Field(default_factory=list)
    unsupported: list[UnsupportedChange] = Field(default_factory=list)
    base_artifact_sha256: str
    submitted_artifact_sha256: str


class _BridgeNode:
    """Internal view of one bridge-shaped node."""

    __slots__ = ("caption", "labels", "node_id", "position", "properties", "style")

    def __init__(
        self,
        node_id: str,
        caption: str,
        position: dict[str, float] | None = None,
        labels: list[str] | None = None,
        properties: dict[str, Any] | None = None,
        style: Any = None,
    ) -> None:
        self.node_id = node_id
        self.caption = caption
        self.position = position or {"x": 0.0, "y": 0.0}
        self.labels = labels or []
        self.properties = properties or {}
        self.style = style

    def identity(self) -> tuple[str, str]:
        """Element identity: (caption,)."""
        return ("element", self.caption)


class _BridgeRelation:
    """Internal view of one bridge-shaped relation."""

    __slots__ = ("from_caption", "properties", "rel_id", "rel_type", "style", "to_caption")

    def __init__(
        self,
        rel_id: str,
        rel_type: str,
        from_caption: str,
        to_caption: str,
        properties: dict[str, Any] | None = None,
        style: Any = None,
    ) -> None:
        self.rel_id = rel_id
        self.rel_type = rel_type
        self.from_caption = from_caption
        self.to_caption = to_caption
        self.properties = properties or {}
        self.style = style

    def identity(self) -> tuple[str, str, str, str]:
        """Relation identity: (type, fromCaption, toCaption)."""
        return ("relation", self.rel_type, self.from_caption, self.to_caption)


def _parse_bridge_graph(graph: dict[str, Any]) -> tuple[
    dict[tuple, _BridgeNode], dict[tuple, _BridgeRelation], list[UnsupportedChange]
]:
    """Parse a bridge-shaped graph into semantic cells + unsupported reports.

    Raises MalformedArrowsGraph if the graph structure is invalid.
    """
    unsupported: list[UnsupportedChange] = []

    if not isinstance(graph, dict):
        raise MalformedArrowsGraph("graph must be a JSON object")

    nodes_in = graph.get("nodes")
    rels_in = graph.get("rels")

    if not isinstance(nodes_in, list):
        raise MalformedArrowsGraph("graph.nodes must be an array")
    if not isinstance(rels_in, list):
        raise MalformedArrowsGraph("graph.rels must be an array")

    nodes: dict[tuple, _BridgeNode] = {}
    seen_captions: dict[str, str] = {}  # caption -> node_id

    for node in nodes_in:
        if not isinstance(node, dict):
            raise MalformedArrowsGraph("each node must be a JSON object")

        node_id = str(node.get("id", ""))
        caption_raw = node.get("caption")
        if caption_raw is None:
            unsupported.append(
                UnsupportedChange(
                    node_id=node_id,
                    reason=R_NO_CAPTION,
                    detail="node has no caption field",
                )
            )
            continue
        caption = str(caption_raw)

        if caption in seen_captions:
            unsupported.append(
                UnsupportedChange(
                    node_id=node_id,
                    reason=R_DUPLICATE_IDENTITY,
                    detail=f"caption {caption!r} already used by node {seen_captions[caption]!r}",
                )
            )
            continue
        seen_captions[caption] = node_id

        position = None
        pos_raw = node.get("position")
        if isinstance(pos_raw, dict):
            position = {
                "x": float(pos_raw.get("x", 0.0)),
                "y": float(pos_raw.get("y", 0.0)),
            }

        labels = node.get("labels")
        if isinstance(labels, list):
            labels = [str(l) for l in labels]
        else:
            labels = []

        properties = node.get("properties")
        if not isinstance(properties, dict):
            properties = {}

        nodes[_BridgeNode(node_id, caption, position, labels, properties).identity()] = _BridgeNode(
            node_id,
            caption,
            position,
            labels,
            properties,
        )

    rels: dict[tuple, _BridgeRelation] = {}

    for rel in rels_in:
        if not isinstance(rel, dict):
            raise MalformedArrowsGraph("each rel must be a JSON object")

        rel_id = str(rel.get("id", ""))
        rel_type = str(rel.get("type", ""))
        from_id = str(rel.get("fromId", ""))
        to_id = str(rel.get("toId", ""))

        # Map fromId/toId to captions via the nodes we parsed
        from_caption = _resolve_caption_by_id(from_id, nodes, seen_captions)
        to_caption = _resolve_caption_by_id(to_id, nodes, seen_captions)

        if from_caption is None or to_caption is None:
            unsupported.append(
                UnsupportedChange(
                    rel_id=rel_id,
                    reason=R_UNRESOLVED_RELATION_ENDPOINT,
                    detail=f"fromId={from_id!r}/toId={to_id!r} did not resolve to captions",
                )
            )
            continue

        properties = rel.get("properties")
        if not isinstance(properties, dict):
            properties = {}

        rels[_BridgeRelation(rel_id, rel_type, from_caption, to_caption, properties).identity()] = (
            _BridgeRelation(rel_id, rel_type, from_caption, to_caption, properties)
        )

    return nodes, rels, unsupported


def _resolve_caption_by_id(
    node_id: str, nodes: dict[tuple, _BridgeNode], seen_captions: dict[str, str]
) -> str | None:
    """Resolve a node id to its caption.

    If the id is not in our nodes dict, search by node_id in seen_captions
    (reverse lookup). Returns None if not found.
    """
    # Try direct match in nodes dict
    for node in nodes.values():
        if node.node_id == node_id:
            return node.caption
    # Reverse lookup
    for caption, nid in seen_captions.items():
        if nid == node_id:
            return caption
    return None


def _compute_graph_sha(graph: dict[str, Any]) -> str:
    """Stable SHA-256 of a bridge graph (sorted, indented JSON)."""
    return hashlib.sha256(
        (json.dumps(graph, indent=2, sort_keys=True) + "\n").encode()
    ).hexdigest()


def classify_arrows(
    base_artifact: bytes, submitted_graph: dict[str, Any], submitted_origin: str
) -> ProjectionDelta:
    """Classify the difference between the base arrows artifact and the
    submitted bridge-shaped graph.

    Both the base and submitted graph are normalized to the bridge shape:
    - base: arrows-v1 artifact → arrows_to_bridge() → bridge shape
    - submitted: must already be in bridge shape (validated strictly)

    Raises:
        NonEmbedOrigin: ``submitted_origin`` is not the exact embed origin.
        MalformedArrowsGraph: the submitted graph is not a valid bridge shape.
    """
    if submitted_origin != ARROWS_EMBED_ORIGIN:
        raise NonEmbedOrigin(
            f"submitted_origin must be exactly {ARROWS_EMBED_ORIGIN!r}"
        )

    # Parse base artifact (arrows-v1 JSON)
    try:
        base_arrows = json.loads(base_artifact.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise MalformedArrowsGraph(f"invalid base arrows artifact JSON: {exc}") from exc

    # Map base to bridge shape
    from archskillkit.projections.arrows_bridge import arrows_to_bridge

    base_bridge = arrows_to_bridge(base_arrows)

    # Parse both sides
    base_nodes, base_rels, base_unsupported_from_parse = _parse_bridge_graph(base_bridge)
    sub_nodes, sub_rels, sub_unsupported_from_parse = _parse_bridge_graph(submitted_graph)

    unsupported: list[UnsupportedChange] = [
        *base_unsupported_from_parse,
        *sub_unsupported_from_parse,
    ]

    candidates: list[SemanticCandidate] = []
    presentation_changes = 0

    submitted_node_idents = set(sub_nodes)
    base_node_idents = set(base_nodes)

    # Elements added (in submitted, not in base)
    for ident in sorted(submitted_node_idents - base_node_idents, key=repr):
        node = sub_nodes[ident]
        candidates.append(
            SemanticCandidate(
                kind="element_added",
                name=node.caption,
                evidence={"id": node.node_id, "labels": node.labels, "properties": node.properties},
            )
        )

    # Elements removed (in base, not in submitted)
    for ident in sorted(base_node_idents - submitted_node_idents, key=repr):
        node = base_nodes[ident]
        candidates.append(
            SemanticCandidate(
                kind="element_removed",
                name=node.caption,
                evidence={"id": node.node_id, "labels": node.labels, "properties": node.properties},
            )
        )

    submitted_rel_idents = set(sub_rels)
    base_rel_idents = set(base_rels)

    # Relations added
    for ident in sorted(submitted_rel_idents - base_rel_idents, key=repr):
        rel = sub_rels[ident]
        candidates.append(
            SemanticCandidate(
                kind="relation_added",
                name=rel.rel_type,
                target=rel.to_caption,
                rel_kind=rel.rel_type,
                evidence={
                    "id": rel.rel_id,
                    "fromCaption": rel.from_caption,
                    "toCaption": rel.to_caption,
                    "properties": rel.properties,
                },
            )
        )

    # Relations removed
    for ident in sorted(base_rel_idents - submitted_rel_idents, key=repr):
        rel = base_rels[ident]
        candidates.append(
            SemanticCandidate(
                kind="relation_removed",
                name=rel.rel_type,
                target=rel.to_caption,
                rel_kind=rel.rel_type,
                evidence={
                    "id": rel.rel_id,
                    "fromCaption": rel.from_caption,
                    "toCaption": rel.to_caption,
                    "properties": rel.properties,
                },
            )
        )

    # Presentation changes: style/properties/position on matched identities
    for ident in sorted(base_node_idents & submitted_node_idents, key=repr):
        base_node = base_nodes[ident]
        sub_node = sub_nodes[ident]
        # Position changes are presentation-only (docs/v2/54 §9)
        if base_node.position != sub_node.position:
            presentation_changes += 1
        # Labels changes on matched elements are presentation
        if base_node.labels != sub_node.labels:
            presentation_changes += 1
        # Properties changes on matched elements are presentation
        if base_node.properties != sub_node.properties:
            presentation_changes += 1

    for ident in sorted(base_rel_idents & submitted_rel_idents, key=repr):
        base_rel = base_rels[ident]
        sub_rel = sub_rels[ident]
        # Style changes on matched relations are presentation
        if base_rel.style != sub_rel.style:
            presentation_changes += 1
        # Properties changes on matched relations are presentation
        if base_rel.properties != sub_rel.properties:
            presentation_changes += 1

    return ProjectionDelta(
        presentation_changes=presentation_changes,
        semantic_changes=len(candidates),
        semantic_candidates=candidates,
        unsupported=unsupported,
        base_artifact_sha256=hashlib.sha256(base_artifact).hexdigest(),
        submitted_artifact_sha256=_compute_graph_sha(submitted_graph),
    )
