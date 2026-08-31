# ADR-0018: SQLite como Code Index inicial

- Status: Accepted
- Date: 2026-08-31

## Context

No hay evidencia para exigir graph DB.

## Decision

Usar SQLite con índices, FTS y queries recursivas.

## Consequences

### Positive

Embedded, portable, simple.

### Negative / Trade-offs

Traversals muy complejos podrían escalar peor.

## Revisit when

Cuando benchmark demuestre bottleneck.
