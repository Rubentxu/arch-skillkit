# ADR-0005: LikeC4 como modelo arquitectónico canónico de V1

- Status: Accepted
- Date: 2026-08-31

## Context

Se necesita una representación textual, versionable, validable y adecuada para arquitectura.

## Decision

LikeC4 será el source of truth arquitectónico de V1. La evidencia raw no desaparece y sigue siendo fuente de provenance.

## Consequences

### Positive

- Evita IR propio.
- Modelado C4 y views.
- Buen encaje con agentes.

### Negative / Trade-offs

- No representa todo el detalle del code graph.
- Acoplamiento conceptual a su DSL durante V1.

## Revisit when

Si las consultas exceden de forma recurrente sus capacidades o aparece necesidad de grafo canónico más rico.
