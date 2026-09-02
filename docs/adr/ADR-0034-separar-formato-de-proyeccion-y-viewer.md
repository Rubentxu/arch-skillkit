# ADR-0034 — Separar Projection Format de Viewer Application

Status: Proposed

## Contexto

V2.2 mezcla parcialmente “formato/aplicación” en routing. GraphML, draw.io o JSON Canvas pueden tener múltiples consumidores; un viewer puede soportar varios formatos.

## Decisión

Mantener `ProjectionAdapter` para generar `ProjectionArtifact` y añadir `ViewerAdapter`/`ViewerRegistry`/`ViewerRouter` para consumirlo.

## Reglas

1. El dominio no conoce aplicaciones concretas.
2. Generar artifact nunca depende de que exista viewer.
3. Viewer selection es capability-driven.
4. Viewer puede ser EMBEDDED, MANAGED_SERVER, LOCAL_PROCESS o WEB_HANDOFF.
5. `SystemDefaultViewer` es fallback.
