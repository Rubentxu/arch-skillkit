# ADR-0033 — Separar ArchitectureSnapshot, RunLedger y RuntimeRegistry

Status: Proposed

## Contexto

Arquitectura aceptada, historial operacional y procesos del SO tienen lifecycles distintos. Guardar PIDs/ports en ArchitectureWorld mezclaría estado efímero con eventos de dominio.

## Decisión

- `ArchitectureSnapshot`: vista inmutable/digest del estado arquitectónico relevante.
- `RunLedger`: historial durable de ejecuciones y métricas.
- `RuntimeRegistry`: estado efímero de viewers/servers/ports bajo XDG runtime.

## Invariantes

- abrir/cerrar viewer no cambia world digest;
- un run puede referenciar snapshot/artifacts por digest;
- RuntimeRegistry puede borrarse sin perder conocimiento.
