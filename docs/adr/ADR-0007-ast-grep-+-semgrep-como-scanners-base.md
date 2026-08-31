# ADR-0007: ast-grep + Semgrep como scanners base

- Status: Accepted
- Date: 2026-08-31

## Context

Se necesita combinar estructura barata y patrones semánticos/framework sin crear parsers.

## Decision

Usar ast-grep para outline/estructura y Semgrep para reglas arquitectónicas. Build metadata complementa ambas.

## Consequences

### Positive

- Multi-language.
- Reglas versionables.
- Menos lecturas LLM.

### Negative / Trade-offs

- No sustituye resolución semántica profunda.
- Puede haber falsos positivos.

## Revisit when

Si SCIP demuestra mejor coste/beneficio para una capacidad concreta.
