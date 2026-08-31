# ADR-0010: Código propio sólo como thin glue

- Status: Accepted
- Date: 2026-08-31

## Context

La ambición del proyecto puede empujar prematuramente a crear CLI, IR, DB y backend.

## Decision

Todo código propio debe limitarse a workspace resolution, orchestration, normalization estrictamente necesaria y doctoring.

## Consequences

### Positive

- Menor superficie.
- Evita reinventar herramientas.
- Arquitectura fácil de entender.

### Negative / Trade-offs

- Algunas optimizaciones quedan diferidas.
- Shell puede llegar a su límite.

## Revisit when

Cuando scripts acumulen lógica, haya problemas de portabilidad o el normalizador sea mediblemente necesario.
