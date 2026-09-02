# ADR-0043 — Separar Semantic State de Presentation State

Status: Proposed

## Contexto

Viewer round-trip introduce posiciones, colores y layout junto con cambios potencialmente arquitectónicos.

## Decisión

- ArchitectureWorld contiene semantic state.
- `PresentationProfile` contiene layout/appearance por viewer/projection.
- import de artifact produce `ProjectionDelta` clasificado.
- semantic candidates se convierten en Proposal; no auto-merge.

## Ejemplos

Presentation: mover caja, waypoints, color.
Semantic: añadir relación, mover componente de bounded context, eliminar datastore.
