# ADR-0001: Mantener el repositorio fuente read-only

- Status: Accepted
- Date: 2026-08-31

## Context

Los assets de análisis no pertenecen al producto que se está analizando y mezclarlos obliga a tocar `.gitignore`, configuración o estructura de proyectos ajenos.

## Decision

ArchSkillKit tratará el repositorio fuente como entrada read-only. Todo estado, evidencia, modelo y visualización se generará fuera del checkout.

## Consequences

### Positive

- Working tree limpio.
- Integración no invasiva.
- Puede analizar repositorios sin permiso de escritura.
- Separación clara producto/proyecto.

### Negative / Trade-offs

- Los assets no viajan automáticamente con el repo.
- Se necesita un registry externo para mapear proyecto y workspace.

## Revisit when

Sólo si aparece un modo explícito opt-in de co-location solicitado por usuarios. Nunca cambiar el default.
