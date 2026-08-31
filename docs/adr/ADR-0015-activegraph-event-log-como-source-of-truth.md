# ADR-0015: ActiveGraph Event Log como source of truth

- Status: Accepted
- Date: 2026-08-31

## Context

LikeC4 no preserva causalidad, claims, forks y approvals.

## Decision

El EventStore pasa a ser fuente de verdad del conocimiento arquitectónico.

## Consequences

### Positive

Replay, lineage, audit, fork/diff.

### Negative / Trade-offs

Migraciones y dependencia runtime.

## Revisit when

Si se sustituye ActiveGraph.
