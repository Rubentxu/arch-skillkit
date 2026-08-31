# ADR-0024: Encapsular ActiveGraph detrás del dominio

- Status: Accepted
- Date: 2026-08-31

## Context

Es dependencia externa y Alpha.

## Decision

No exponer tipos ActiveGraph fuera del adapter/domain boundary.

## Consequences

### Positive

Reduce lock-in.

### Negative / Trade-offs

Mapping adicional.

## Revisit when

Si deliberadamente pasa a ser API pública.
