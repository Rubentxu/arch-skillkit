# Backlog V2

## Now — cerrar V2.1

| Trabajo | Estado | Criterio de salida |
|---|---|---|
| Baseline reproducible | Locally verified; local workflow pending | Python y BATS verdes con `just ci-github-local` |
| Checkpoint de performance | Partial | benchmark ingest/query/context/memoria y KPI guardados; falta instalación |
| UAT V2.1 | Pending | UAT2 obligatorios ejecutados y evidencia consolidada |
| SCIP spike | Pending / conditional | adopt/optional/reject documentado con benchmark |
| Cierre/release V2.1 | Pending | gates cerrados; SemVer, changelog y tag coherentes |

## Implementado — baseline local verificado; gates de release pendientes

- Python + ActiveGraph, packs y EventStore por proyecto.
- Code Index con ingestión ast-grep/Semgrep y query API.
- Evidence/Observation, Claim lifecycle, mapper y reviewer.
- ContextPack/Compiler implementado; KPI medido y PASS al 99,0% para 100 archivos × 10 iteraciones (10 lecturas frente a 1.000).
- LikeC4/Arrows, drift/stale model y fork/diff/promote/reject.

## Next — V2.2 por slices tras cerrar V2.1

1. JSON Canvas writer + fixtures + tests + UAT.
2. GraphML writer + compatibilidad de consumidores + UAT.
3. draw.io writer + IDs estables + UAT.
4. Redacción productiva.
5. Thresholds y routing productivo.

Foundation, router inicial, lifecycle y adapters LikeC4/Arrows ya están parcialmente presentes. El orden de formatos podrá cambiar con evidencia del checkpoint; no se implementarán en paralelo sin cerrar cada slice.

## Deferred

- incremental Git, co-change y test impact;
- OpenAPI, Kubernetes y runtime telemetry;
- graph DB, CodeQL, UI, SaaS y organization graph.

Fuente de estado: [`STATUS.md`](STATUS.md).
