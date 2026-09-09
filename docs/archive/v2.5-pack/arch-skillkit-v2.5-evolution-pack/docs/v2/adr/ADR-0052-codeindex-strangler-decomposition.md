# ADR-0052 — CodeIndex Strangler Decomposition

Status: Proposed

## Decision

No reemplazar CodeIndex de golpe. Extraer en orden:

1. provider ingestion;
2. evidence store;
3. query adapter;
4. compatibility facade.

## Verification

Fixtures actuales deben mantener resultados semánticos antes/después.
