# Roadmap V2

Fuente de estado detallada: [`STATUS.md`](STATUS.md). `Local suite green` indica verificación reproducible local del 2026-09-01; no implica UAT, KPI, release ni validación del workflow local con `act`.

## Tracker V2.1

| Fase | Alcance | Estado | Siguiente gate |
|---|---|---|---|
| A | ActiveGraph foundation | Implemented; local suite green | replay + aislamiento UAT |
| B | Code Index | Implemented; local suite green | ingest/query UAT |
| C | Evidence → Architecture | Implemented; local suite green | provenance y contradicción UAT |
| D | Context Compiler | KPI PASS para carga canónica | consolidar UAT2-007/008/017 y medir instalación |
| E | LikeC4 + Arrows | Implemented; local suite green | regeneración UAT |
| F | Drift, contradicción, stale model | Implemented; local suite green | UAT determinista |
| G | Fork/diff/promote/reject | Implemented; local suite green | UAT de aislamiento y aprobación |
| H | SCIP spike | Pending / conditional | decidir con métricas, no por anticipación |
| I | Performance & architecture checkpoint | Partial | instalación y evidencia UAT obligatoria pendientes |

## Gates de cierre V2.1

1. [x] Entorno local reproducible con Python 194/194 y BATS 69/69 verdes.
2. [ ] Medición de instalación; el benchmark de ingest, query, Context Compiler y memoria está guardado para la carga canónica de 100 archivos × 10 iteraciones.
3. [ ] Evidencia consolidada de los UAT obligatorios de [`18-uat-v2.md`](18-uat-v2.md). El KPI del Context Compiler está medido y PASS al 99,0% (10 frente a 1.000 lecturas), pero no cierra ese gate por sí solo.
4. [ ] Ejecución local del workflow con `just ci-github-local` y decisión de compatibilidad entre Python `>=3.11` y el baseline `3.12.11`.
5. [ ] Decisión SCIP basada en el baseline.
6. [ ] Reconciliación de release: paquete `0.2.0.dev0`, changelog y tag (actualmente sólo existe `v0.1.0`).

## Continuación V2.2

V2.2 está **Partial**: foundation, lifecycle parcial, router inicial y adapters LikeC4/Arrows están implementados. draw.io, JSON Canvas, GraphML, redacción y thresholds/routing productivo quedan pendientes. Las especificaciones del bundle de integración ya están absorbidas en `docs/v2/`; el bundle no es canónico. Se continuará después del gate V2.1, por slices verticales; ver [`37-roadmap-v2.2.md`](37-roadmap-v2.2.md).

## Releases

La antigua secuencia v0.5–v1.0 era una previsión y no describe los artefactos publicados. Las iniciativas V2.1/V2.2 y el SemVer del paquete se siguen por separado en [`STATUS.md`](STATUS.md). No se asignará una versión de release a V2.1 hasta cerrar sus gates.
