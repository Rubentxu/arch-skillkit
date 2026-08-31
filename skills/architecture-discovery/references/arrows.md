# Arrows Projections

Arrows is the exploratory, detailed projection of the evidence (docs/12).
It is NOT the source of truth: the canonical model lives in LikeC4. Arrows
may be more detailed than the model, but must never contradict it — every
node and relationship here derives from the same raw evidence the Modeler
used, and keeps provenance so the Review role can audit consistency.

## Schema (OQ-05 resolution)

Every `.arrows` file is JSON with the minimal, stable property-graph schema
`arch-skillkit/arrows-v1`:

```json
{
  "schema": "arch-skillkit/arrows-v1",
  "generated_by": "export-arrows.sh",
  "title": "Endpoints",
  "source": { "project_id": "...", "commit": "...", "generated_at": "..." },
  "nodes": [
    { "id": "node:src/Http.kt:11", "labels": ["Endpoint"],
      "properties": { "rule": "spring.endpoint", "location": "src/Http.kt:11" } }
  ],
  "relationships": [
    { "id": "rel:...", "type": "DECLARED_IN", "start": "...", "end": "...", "properties": {} }
  ]
}
```

Node ids are stable across reruns (derived from evidence location, not
order). Import into arrows.app is a deferred adapter (ADR-0006: the
projection layer is replaceable); the schema is designed to map trivially
onto a property graph.

## Views (generated only when the evidence exists)

| File | Source evidence | Content |
|---|---|---|
| `overview.arrows` | always | project node + detected build systems |
| `dependencies.arrows` | cargo metadata / package.json | crates and npm dependencies (`DEPENDS_ON`) |
| `endpoints.arrows` | semgrep `*.endpoint` | endpoints per source file (`DECLARED_IN`) |
| `messaging.arrows` | semgrep `*messaging*` | consumers/listeners |
| `data-access.arrows` | semgrep `*persistence*` | data-access ports |

Known limitations (documented, by design in V1): endpoint labels use
`file:line` locations because semgrep OSS gates code snippets; route paths
can be added later when metavariables are exposed or by agent enrichment.
No `ports-adapters` view: the outline evidence does not yet capture
trait-implementations (that is SCIP territory, deferred per docs/16 E2).

## Procedure

After the scan and before/with modeling, run `scripts/export-arrows.sh`.
Re-runs overwrite the generated views in place (they are derived data);
nothing in `knowledge/` or `likec4/` is touched.
