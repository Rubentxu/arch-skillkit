# ADR-0030: Mantener proyecciones unidireccionales en V2.2

- Status: Accepted
- Date: 2026-08-31

## Context

Las aplicaciones externas permiten edición manual, pero importar cambios añade conflictos y autoridad bidireccional.

## Decision

V2.2 genera proyecciones one-way y protege ediciones manuales contra sobrescritura.

## Consequences

### Positive

Modelo de autoridad claro y simple.

### Negative / Trade-offs

Cambios manuales no vuelven automáticamente al Architecture World.

## Revisit when

Cuando usuarios demuestren necesidad real de round-trip.
