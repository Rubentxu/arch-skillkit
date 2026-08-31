# ADR-0006: Arrows como proyección exploratoria

- Status: Accepted
- Date: 2026-08-31

## Context

LikeC4 no debe llenarse con funciones, handlers, endpoints y edges de bajo nivel.

## Decision

Arrows se usará para grafos detallados derivados de evidencia/modelo, sin convertirse en truth source.

## Consequences

### Positive

- Exploración rica.
- Mantiene C4 legible.
- Sustituible.

### Negative / Trade-offs

- Dos outputs a mantener coherentes.
- Requiere reviewer de contradicciones.

## Revisit when

Si otro renderer ofrece mejor workflow sin romper el pipeline.
