# UAT V2.2

## UAT-P01 — Projection is external

No artifact generated inside source repo.

## UAT-P02 — LikeC4 regeneration

Delete projection, regenerate from Architecture World.

Semantically equivalent.

## UAT-P03 — Arrows validity

Generated `.arrows` opens without manual repair.

## UAT-P04 — JSON Canvas validity

Generated `.canvas` opens in a compatible JSON Canvas application.

## UAT-P05 — Knowledge map

Generate bounded-context knowledge map containing:

- summary;
- decisions;
- dependencies;
- evidence links.

## UAT-P06 — GraphML portability

Same GraphML opens in:

- Cytoscape;
- Gephi;
- yEd.

No application-specific export required.

## UAT-P07 — Large graph routing

Large dependency graph routes to GraphML, not Arrows.

## UAT-P08 — draw.io validity

Generated `.drawio` opens and remains editable.

## UAT-P09 — draw.io stable IDs

Rerun preserves stable semantic IDs where source elements remain.

## UAT-P10 — VisualIntent routing

Test matrix routes expected destination.

## UAT-P11 — User override

User can force another compatible projection.

## UAT-P12 — Manual edit protection

Modified artifact is not silently overwritten.

## UAT-P13 — Staleness

Architecture change marks affected projection stale.

## UAT-P14 — Security redaction

Shareable/public profiles omit configured sensitive metadata.

## UAT-P15 — Projection deletion safety

Deleting every generated projection leaves source knowledge intact.

## UAT-P16 — Multi-project isolation

Projection artifacts never mix between project workspaces.

## UAT-P17 — Proposal projection

Forked architecture proposal generates independent draw.io/canvas output.

## UAT-P18 — No renderer leakage

Domain tests do not import application-specific libraries/APIs.
