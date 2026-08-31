# ADR-0011: SCIP y CodeQL quedan diferidos

- Status: Accepted
- Date: 2026-08-31

## Context

Ambas herramientas aportan análisis más profundo, pero incrementan complejidad y coste.

## Decision

SCIP se evaluará como spike para resolución semántica; CodeQL será opt-in para dataflow/security. Ninguno es requisito V1.

## Consequences

### Positive

- MVP simple.
- Se conservan caminos de evolución.
- Coste alineado con necesidad.

### Negative / Trade-offs

- V1 puede requerir targeted reads adicionales.
- Menor precisión cross-file en algunos casos.

## Revisit when

Tras validación real-world y medición de targeted reads/ambiguity.
