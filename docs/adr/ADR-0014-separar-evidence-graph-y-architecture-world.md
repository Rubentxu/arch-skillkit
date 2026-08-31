# ADR-0014: Separar Evidence Graph y Architecture World

- Status: Accepted
- Date: 2026-08-31

## Context

Code facts y conocimiento arquitectónico tienen granularidad y lifecycle distintos.

## Decision

Usar code.sqlite regenerable y ActiveGraph persistente.

## Consequences

### Positive

Mejor escalabilidad conceptual y event log semántico.

### Negative / Trade-offs

Dos stores y mapping entre ellos.

## Revisit when

Si un único store demuestra cubrir ambos workloads.
