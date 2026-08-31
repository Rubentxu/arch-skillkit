# ADR-0013: Adoptar Python + ActiveGraph como runtime V2

- Status: Accepted
- Date: 2026-08-31

## Context

La V2 necesita event sourcing, replay, fork/diff, policies, behaviors y provenance.

## Decision

Adoptar Python como lenguaje principal y ActiveGraph encapsulado detrás del dominio.

## Consequences

### Positive

Reduce código propio y habilita funcionalidades diferenciales.

### Negative / Trade-offs

Framework joven y Python puede no servir para hot paths.

## Revisit when

Si ActiveGraph incumple contratos esenciales o performance/estabilidad bloquean el producto.
