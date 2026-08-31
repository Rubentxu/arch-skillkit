# ADR-0023: Go queda deferido como accelerator

- Status: Rejected
- Date: 2026-08-31

## Context

ActiveGraph reduce necesidad de core Go.

## Decision

No escribir Go hasta triggers cuantificados.

## Consequences

### Positive

Evita doble stack prematuro.

### Negative / Trade-offs

Posible cuello descubierto tarde.

## Revisit when

Cuando triggers de performance/distribution se cumplan.

## Resolution

Esta línea queda cerrada por ADR-0025.

No se contempla Go como accelerator, indexer, CLI ni evolución propia del producto.
