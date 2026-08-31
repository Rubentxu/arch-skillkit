# Architecture Drift

## Definition

Diferencia entre arquitectura aceptada/declarada y evidencia actual.

## Types

- structural drift;
- missing architecture;
- stale architecture;
- boundary violation;
- technology drift.

## Example

Rule:

`Domain MUST NOT depend_on Infrastructure`

Observation:

`domain.OrderService CALLS postgres.PostgresRepository`

Finding:

- kind: architecture_drift
- severity: high
- evidence: edge
- introduced_commit: SHA

## Rule

El LLM puede explicar/proponer, pero no debe ser necesario para detectar una regla determinista.
