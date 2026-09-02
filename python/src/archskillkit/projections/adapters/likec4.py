"""LikeC4 projection adapter (M2-E1, docs/v2/28, ADR-0016).

Renders the Architecture World as a LikeC4 model whose structure mirrors
the V1 golden template (skills/architecture-discovery/templates/model.c4)
so the output validates by construction with the pinned likec4.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from archskillkit.projections.contract import (
    ProjectionContext,
    ProjectionMetrics,
    ProjectionResult,
)
from archskillkit.projections.intents import IntentType, VisualIntent

# element category (docs/v2/04) → LikeC4 specification kind, following
# the golden template vocabulary.
_KIND_TO_LIKEC4 = {
    "component": "container",
    "container": "container",
    "bounded_context": "container",
    "system": "system",
    "external_system": "externalSystem",
    "datastore": "interface",
    "topic": "interface",
    "interface": "interface",
}

_INTERNAL = {"component", "container", "bounded_context", "system",
             "datastore", "topic", "interface"}

_ORIGIN_TAG = {"DETECTED": "#detected", "INFERRED": "#inferred",
               "DECLARED": "#declared", "OBSERVED": "#detected"}
_CONFIDENCE_TAG = {"high": "#confidence-high", "medium": "#confidence-medium",
                   "low": "#confidence-low"}

_SPECIFICATION = """\
specification {
  element actor
  element system
  element container
  element externalSystem
  element datastore
  element queue
  element interface
  tag interface
  tag detected
  tag inferred
  tag declared
  tag confidence-high
  tag confidence-medium
  tag confidence-low
}"""


def _quote(text: str) -> str:
    return text.replace("'", "")


class LikeC4Adapter:
    name = "likec4"
    supported_intents = frozenset(
        {"architecture"} & set(IntentType.__args__))  # type: ignore[attr-defined]
    version = "0.1.0"

    def project(self, intent: VisualIntent,
                context: ProjectionContext) -> ProjectionResult:
        artifact = context.annotations.get("artifact")
        if not artifact:
            raise ValueError("likec4 adapter requires annotations['artifact']")
        snap = context.snapshot
        elements: list[dict[str, Any]] = list(snap.get("elements", []))
        relations: list[dict[str, Any]] = list(snap.get("relations", []))

        lines: list[str] = [
            "// ArchSkillKit V2 projection — regenerated from the",
            "// Architecture World event log (ADR-0016). Do not hand-edit:",
            "// manual edits are protected and block regeneration.",
            _SPECIFICATION,
            "",
            "model {",
        ]

        # Track where each element lives so relations can use the right
        # FQN: internals are nested inside `target` and must be referenced
        # as `target.<id>` from the outer scope (likec4 silently rejects
        # bare ids at the model-root scope for nested elements).
        ids: dict[str, str] = {}
        scopes: dict[str, str] = {}  # ident -> "target" or ""
        internals = sorted((e for e in elements if e["kind"] in _INTERNAL),
                           key=lambda e: e["name"])
        externals = sorted((e for e in elements if e["kind"] not in _INTERNAL),
                           key=lambda e: e["name"])

        lines.append(
            f"  target = system '{_quote(snap.get('project_name', 'Analyzed System'))}' {{")
        for index, element in enumerate(internals):
            ident = f"n{index}"
            ids[element["name"]] = ident
            scopes[ident] = "target"
            lines.append(f"    {ident} = {_KIND_TO_LIKEC4[element['kind']]}"
                         f" '{_quote(element['name'])}' {{")
            interface_tag = "#interface " \
                if element["kind"] == "interface" else ""
            lines.append(f"      {interface_tag}"
                         f"{_ORIGIN_TAG.get(element['origin'], '#detected')}"
                         f" {_CONFIDENCE_TAG.get(element['confidence'], '#confidence-high')}")
            lines.append("    }")
        lines.append("  }")

        for index, element in enumerate(externals):
            ident = f"x{index}"
            ids[element["name"]] = ident
            scopes[ident] = ""
            lines.append(f"  {ident} = {_KIND_TO_LIKEC4[element['kind']]}"
                         f" '{_quote(element['name'])}' {{")
            lines.append(f"    {_ORIGIN_TAG.get(element['origin'], '#detected')}"
                         f" {_CONFIDENCE_TAG.get(element['confidence'], '#confidence-high')}")
            lines.append("  }")

        for relation in sorted(relations,
                               key=lambda r: (r["kind"], r["source"], r["target"])):
            src = ids.get(relation["source"])
            dst = ids.get(relation["target"])
            if not src or not dst:
                continue
            src_ref = f"{scopes[src]}.{src}" if scopes[src] else src
            dst_ref = f"{scopes[dst]}.{dst}" if scopes[dst] else dst
            lines.append(f"  {src_ref} -> {dst_ref} '{_quote(relation['kind'])}' {{")
            lines.append("    #detected"
                         f" {_CONFIDENCE_TAG.get(relation.get('confidence', 'high'), '#confidence-high')}")
            lines.append("  }")

        lines.extend([
            "}",
            "",
            "views {",
            "  view index {",
            "    title 'Architecture'",
            "    include *",
            "  }",
            "}",
            "",
        ])

        path = Path(artifact)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines))

        warnings: list[str] = []
        if len(ids) != len(elements):
            warnings.append("some elements could not be rendered (missing endpoints)")

        return ProjectionResult(
            format=self.name,
            path=str(path),
            source_snapshot={
                "architecture_run": context.architecture_run,
                "code_index_revision": context.code_index_revision,
            },
            warnings=warnings,
            metrics=ProjectionMetrics(
                nodes=len(ids),
                edges=sum(1 for r in relations
                          if r["source"] in ids and r["target"] in ids),
            ),
        )
