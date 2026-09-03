"""draw.io ProjectionDelta classifier (V2.4 M5 slice 23b).

Pure function module: parses draw.io XML (base artifact vs submitted
export) and classifies every difference as presentation-only or
semantic. NO I/O, NO world access, NO http imports — the delivery layer
(23c) owns transport, auth and origin enforcement at its boundary, and
this module still refuses non-embed origins by contract (design §A.3).

Empirical rules proven by slice 23a (scripts/uat/m5-slice-23a/README.md):

- R2: metadata keys are XML-valid kebab-case: ``archskillkit-element-*``
  on ``UserObject`` vertices, ``archskillkit-relation-*`` on flat
  ``mxCell`` edges. ``value``/``label`` are presentation — never parsed.
- R5: the merge channel preserves ``UserObject`` + custom attributes, so
  submitted exports carry the metadata this classifier needs.
- R8: a leading empty page from ``load(blank)`` is noise and is ignored.

Classification (docs/v2/54 §9):

- semantic:   element/relation added or removed, element kind changed.
              An element RENAME is never aliased: different identity key
              ⇒ natural remove+add pair of candidates.
- presentation: style/geometry-only diffs, metadata-less edges, scaffold
              cells, empty pages.

Anything ambiguous lands in ``unsupported`` (stable reason codes); the
delivery layer must refuse to fork while ``unsupported`` is non-empty
(docs/v2/54 §8: never accept a diagram edit as architecture
automatically).
"""

from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from archskillkit.projections.adapters.drawio import ELEMENT_KINDS

DELTA_SCHEMA = "arch-skillkit/drawio-delta-v1"

# docs/v2/54 §12 / design §A: the only origin a submitted export may
# come from. Enforced here as defence in depth on top of the delivery
# layer's own postMessage/HTTP validation.
DRAWIO_EMBED_ORIGIN = "https://embed.diagrams.net"

SemanticKind = Literal[
    "element_added",
    "element_removed",
    "relation_added",
    "relation_removed",
    "element_kind_changed",
]

# Stable reason codes for ambiguous cells (delivery maps them to 422).
R_NO_VERTEX_NAME = "NO_VERTEX_NAME"
R_UNKNOWN_ELEMENT_KIND = "UNKNOWN_ELEMENT_KIND"
R_INCOMPLETE_RELATION = "INCOMPLETE_RELATION"
R_UNRESOLVED_ENDPOINT = "UNRESOLVED_RELATION_ENDPOINT"
R_DUPLICATE_IDENTITY = "DUPLICATE_IDENTITY"
R_AMBIGUOUS_CELL = "AMBIGUOUS_CELL"


class DrawioDeltaError(ValueError):
    """Raised when the submitted payload cannot be classified at all."""

    code = "DRAWIO_DELTA_ERROR"


class NonEmbedOrigin(DrawioDeltaError):
    code = "NON_EMBED_ORIGIN"


class MalformedDrawioXml(DrawioDeltaError):
    code = "MALFORMED_XML"


class SemanticCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: SemanticKind
    name: str
    target: str | None = None
    rel_kind: str | None = None
    confidence: Literal["high", "medium", "low"] = "high"
    evidence: dict[str, Any] = Field(default_factory=dict)


class UnsupportedCell(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cell_id: str
    reason: str
    detail: str = ""


class ProjectionDelta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema: Literal["arch-skillkit/drawio-delta-v1"] = DELTA_SCHEMA  # type: ignore[assignment]
    presentation_changes: int
    semantic_changes: int
    semantic_candidates: list[SemanticCandidate] = Field(default_factory=list)
    unsupported: list[UnsupportedCell] = Field(default_factory=list)
    base_artifact_sha256: str
    submitted_artifact_sha256: str


class _ParsedCell:
    """Internal semantic view of one draw.io cell."""

    __slots__ = (
        "cell_id",
        "element_kind",
        "element_name",
        "geometry",
        "raw",
        "relation_kind",
        "relation_source",
        "relation_target",
        "style",
    )

    def __init__(
        self,
        cell_id: str,
        *,
        element_name: str | None = None,
        element_kind: str | None = None,
        relation_kind: str | None = None,
        relation_source: str | None = None,
        relation_target: str | None = None,
        style: str = "",
        geometry: str = "",
        raw: dict[str, Any] | None = None,
    ) -> None:
        self.cell_id = cell_id
        self.element_name = element_name
        self.element_kind = element_kind
        self.relation_kind = relation_kind
        self.relation_source = relation_source
        self.relation_target = relation_target
        self.style = style
        self.geometry = geometry
        self.raw = raw or {}

    @property
    def is_vertex(self) -> bool:
        return self.element_name is not None

    @property
    def is_edge(self) -> bool:
        return self.relation_kind is not None

    def identity(self) -> tuple:
        if self.is_vertex:
            return ("element", self.element_name)
        return ("relation", self.relation_kind, self.relation_source, self.relation_target)

    def signature(self) -> tuple:
        """Semantic signature: identity + kind (kind changes are semantic)."""
        ident = self.identity()
        if ident[0] == "element":
            return ident + (self.element_kind,)
        return ident

    def style_geometry(self) -> tuple[str, str]:
        return (self.style, self.geometry)


def _geometry_text(cell_el: ET.Element) -> str:
    geo = cell_el.find("mxGeometry")
    if geo is None:
        return ""
    return ET.tostring(geo, encoding="unicode")


def _extract_cells(xml_bytes: bytes) -> tuple[dict[tuple, _ParsedCell], list[UnsupportedCell]]:
    """Parse one XML document into semantic cells + unsupported reports.

    Raises MalformedDrawioXml on parse failure.
    """
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise MalformedDrawioXml(f"invalid draw.io XML: {exc}") from exc

    cells: dict[tuple, _ParsedCell] = {}
    unsupported: list[UnsupportedCell] = []
    seen_vertex_names: dict[str, str] = {}
    # mxCell elements consumed as UserObject children — excluded from the
    # bare-mxCell pass below (root.iter() yields both).
    consumed: set[int] = set()

    for el in root.iter():
        if el.tag == "UserObject":
            cell_id = el.get("id") or ""
            name = el.get("archskillkit-element-name")
            kind = el.get("archskillkit-element-kind")
            cell_el = el.find("mxCell")
            if cell_el is not None:
                consumed.add(id(cell_el))
            style = (cell_el.get("style") or "") if cell_el is not None else ""
            geometry = _geometry_text(cell_el) if cell_el is not None else ""
            raw = {
                "id": cell_id,
                "archskillkit-element-name": name,
                "archskillkit-element-kind": kind,
            }
            if not name:
                unsupported.append(
                    UnsupportedCell(
                        cell_id=cell_id,
                        reason=R_NO_VERTEX_NAME,
                        detail="UserObject vertex without archskillkit-element-name",
                    )
                )
                continue
            if kind not in ELEMENT_KINDS:
                unsupported.append(
                    UnsupportedCell(
                        cell_id=cell_id,
                        reason=R_UNKNOWN_ELEMENT_KIND,
                        detail=f"element kind {kind!r} outside the adapter's known set",
                    )
                )
                continue
            if name in seen_vertex_names and seen_vertex_names[name] != cell_id:
                unsupported.append(
                    UnsupportedCell(
                        cell_id=cell_id,
                        reason=R_DUPLICATE_IDENTITY,
                        detail=f"element name {name!r} already used by cell "
                        f"{seen_vertex_names[name]}",
                    )
                )
                continue
            seen_vertex_names[name] = cell_id
            cell = _ParsedCell(
                cell_id,
                element_name=name,
                element_kind=kind,
                style=style,
                geometry=geometry,
                raw=raw,
            )
            cells[cell.identity()] = cell

    for el in root.iter():
        if el.tag != "mxCell" or id(el) in consumed:
            continue
        cell_id = el.get("id") or ""
        is_vertex = el.get("vertex") == "1"
        is_edge = el.get("edge") == "1"
        if is_vertex and is_edge:
            unsupported.append(
                UnsupportedCell(
                    cell_id=cell_id,
                    reason=R_AMBIGUOUS_CELL,
                    detail="cell declares vertex and edge simultaneously",
                )
            )
            continue
        if is_vertex:
            # Vertices are only semantic under UserObject (R2/R5); a bare
            # vertex cell has no identity channel → unsupported.
            unsupported.append(
                UnsupportedCell(
                    cell_id=cell_id,
                    reason=R_NO_VERTEX_NAME,
                    detail="bare mxCell vertex (metadata only survives on UserObject vertices)",
                )
            )
            continue
        if not is_edge:
            continue  # scaffold (id 0/1), layer or group cell

        rel_kind = el.get("archskillkit-relation-kind")
        rel_src = el.get("archskillkit-relation-source-name")
        rel_tgt = el.get("archskillkit-relation-target-name")
        present = [v for v in (rel_kind, rel_src, rel_tgt) if v]
        if not present:
            # Metadata-less edge: presentation-only connection.
            continue
        if not (rel_kind and rel_src and rel_tgt):
            unsupported.append(
                UnsupportedCell(
                    cell_id=cell_id,
                    reason=R_INCOMPLETE_RELATION,
                    detail="edge carries partial archskillkit-relation-* metadata",
                )
            )
            continue
        raw = {
            "id": cell_id,
            "archskillkit-relation-kind": rel_kind,
            "archskillkit-relation-source-name": rel_src,
            "archskillkit-relation-target-name": rel_tgt,
        }
        cell = _ParsedCell(
            cell_id,
            relation_kind=rel_kind,
            relation_source=rel_src,
            relation_target=rel_tgt,
            style=el.get("style") or "",
            geometry=_geometry_text(el),
            raw=raw,
        )
        cells[cell.identity()] = cell

    return cells, unsupported


def classify_xml(
    base_artifact: bytes, submitted_xml: str, submitted_origin: str
) -> ProjectionDelta:
    """Classify the difference between the base artifact and the
    submitted draw.io export.

    Raises:
        NonEmbedOrigin: ``submitted_origin`` is not the exact draw.io
            embed origin.
        MalformedDrawioXml: either side is not well-formed XML.
    """
    if submitted_origin != DRAWIO_EMBED_ORIGIN:
        raise NonEmbedOrigin(f"submitted_origin must be exactly {DRAWIO_EMBED_ORIGIN!r}")

    base_cells, _base_unsupported = _extract_cells(base_artifact)
    sub_cells, unsupported = _extract_cells(submitted_xml.encode("utf-8"))

    candidates: list[SemanticCandidate] = []
    presentation_changes = 0

    # Endpoint resolution: submitted relation endpoints must name vertices
    # known in the submitted model (or surviving from base).
    known_vertex_names = {ident[1] for ident, cell in sub_cells.items() if cell.is_vertex} | {
        ident[1] for ident, cell in base_cells.items() if cell.is_vertex
    }

    submitted_idents = set(sub_cells)
    base_idents = set(base_cells)

    for ident in sorted(submitted_idents - base_idents, key=repr):
        cell = sub_cells[ident]
        if cell.is_vertex:
            candidates.append(
                SemanticCandidate(
                    kind="element_added", name=cell.element_name or "", evidence=dict(cell.raw)
                )
            )
        else:
            if cell.relation_source not in known_vertex_names or (
                cell.relation_target not in known_vertex_names
            ):
                unsupported.append(
                    UnsupportedCell(
                        cell_id=cell.cell_id,
                        reason=R_UNRESOLVED_ENDPOINT,
                        detail=f"relation endpoints "
                        f"{cell.relation_source!r}→{cell.relation_target!r} "
                        f"not resolvable to known vertices",
                    )
                )
                continue
            candidates.append(
                SemanticCandidate(
                    kind="relation_added",
                    name=cell.relation_kind or "",
                    target=cell.relation_target,
                    rel_kind=cell.relation_kind,
                    evidence=dict(cell.raw),
                )
            )

    for ident in sorted(base_idents - submitted_idents, key=repr):
        cell = base_cells[ident]
        if cell.is_vertex:
            candidates.append(
                SemanticCandidate(
                    kind="element_removed", name=cell.element_name or "", evidence=dict(cell.raw)
                )
            )
        else:
            candidates.append(
                SemanticCandidate(
                    kind="relation_removed",
                    name=cell.relation_kind or "",
                    target=cell.relation_target,
                    rel_kind=cell.relation_kind,
                    evidence=dict(cell.raw),
                )
            )

    for ident in sorted(base_idents & submitted_idents, key=repr):
        base_cell = base_cells[ident]
        sub_cell = sub_cells[ident]
        # Same identity, different kind → semantic change (vertices only:
        # a relation's kind triple IS its identity, so matched edges are
        # always signature-equal).
        if base_cell.is_vertex and base_cell.signature() != sub_cell.signature():
            candidates.append(
                SemanticCandidate(
                    kind="element_kind_changed",
                    name=base_cell.element_name or "",
                    evidence={
                        "id": sub_cell.cell_id,
                        "old_kind": base_cell.element_kind,
                        "new_kind": sub_cell.element_kind,
                    },
                )
            )
            continue
        # Same semantics: style/geometry differences are presentation.
        if base_cell.style_geometry() != sub_cell.style_geometry():
            presentation_changes += 1

    # Metadata-less edges: a presence change is a presentation change
    # (connection drawn/removed by hand carries no semantic identity).
    base_plain_edges = _count_plain_edges(base_artifact)
    sub_plain_edges = _count_plain_edges(submitted_xml.encode("utf-8"))
    if base_plain_edges != sub_plain_edges:
        presentation_changes += abs(sub_plain_edges - base_plain_edges)

    return ProjectionDelta(
        presentation_changes=presentation_changes,
        semantic_changes=len(candidates),
        semantic_candidates=candidates,
        unsupported=unsupported,
        base_artifact_sha256=hashlib.sha256(base_artifact).hexdigest(),
        submitted_artifact_sha256=hashlib.sha256(submitted_xml.encode("utf-8")).hexdigest(),
    )


def _count_plain_edges(xml_bytes: bytes) -> int:
    """Count mxCell edges carrying NO archskillkit metadata at all."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return 0
    count = 0
    for el in root.iter():
        if (
            el.tag == "mxCell"
            and el.get("edge") == "1"
            and not any(k.startswith("archskillkit-") for k in el.attrib)
        ):
            count += 1
    return count
