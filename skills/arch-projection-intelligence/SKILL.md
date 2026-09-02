---
name: arch-projection-intelligence
description: Plan and enrich architecture projections without coupling reasoning to a renderer. Use when asked to visualize, explain, compare or create architecture views for LikeC4, Arrows, draw.io, JSON Canvas, GraphML, Excalidraw or other supported viewers.
---

# Projection Intelligence

## Rule

Reason in `VisualIntent` + `ProjectionEnrichment`, not renderer syntax.

## Workflow

1. Resolve audience/intent/subject.
2. Compile bounded architecture/evidence context.
3. Select focus, overlays and grouping.
4. Request ProjectionAdapter by format or let router decide.
5. Select ViewerAdapter independently.
6. Report unsupported enrichment capabilities as warnings.

## Never

- treat layout changes as architectural changes;
- write accepted architecture from a diagram edit;
- assume LikeC4 is the only viewer.
