# Backlog V2.2

## Implemented — local suite green

Verificación local reproducible aprobada el 2026-09-01; UAT y la ejecución del workflow local con `act` siguen pendientes.

- VisualIntent schema.
- ProjectionAdapter protocol y ProjectionResult.
- Projection metadata.
- LikeC4 y Arrows adapter normalization.
- Stale detection y manual-edit protection.
- Routing inicial por intent y user override.

## Next — slices verticales

1. JSON Canvas projector + fixtures + UAT.
2. GraphML projector + perfiles de consumidor + UAT.
3. draw.io projector + stable IDs + UAT.
4. Security/redaction profiles verificados.
5. Size thresholds y routing productivo.
6. Validación real en Rust, Kotlin/Java y TypeScript.

## Después del core

- projection previews/reports
- proposal projections
- investigation canvas

## Could

- Excalidraw projector
- Mermaid Chart exporter
- Structurizr alternative exporter
- BPMN specialized projection
- temporal GEXF exporter

## Deferred

- bidirectional import
- custom visualization UI
- renderer plugin marketplace
- Cytoscape-specific API integration
- Gephi-specific API integration
- yEd-specific API integration

Este backlog gestiona las especificaciones absorbidas del bundle de integración; no se mantiene un backlog paralelo dentro del bundle. Estado global: [`STATUS.md`](STATUS.md).
