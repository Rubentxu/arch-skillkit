# ADR-0026: Introducir VisualIntent y Projection Router

- Status: Accepted
- Date: 2026-08-31

## Context

Los agentes no deben acoplarse a herramientas concretas de visualización.

## Decision

Definir una intención semántica y enrutarla hacia el projector más adecuado.

## Consequences

### Positive

Reduce acoplamiento y permite sustituir aplicaciones.

### Negative / Trade-offs

Añade una pequeña capa de routing.

## Revisit when

Si la selección automática demuestra ser menos útil que una selección explícita siempre.
