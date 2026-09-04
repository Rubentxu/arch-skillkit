# ADR-0052 — CodeIndex Strangler Decomposition

Status: Accepted

## Verification evidence

`python/src/archskillkit/codeindex.py:117` — `CodeIndex` class provides the canonical evidence store; the strangler decomposition proceeds by extracting provider ingestion, evidence store, query adapter, and compatibility facade in order.

## Decision

No reemplazar CodeIndex de golpe. Extraer en orden:

1. provider ingestion;
2. evidence store;
3. query adapter;
4. compatibility facade.

## Verification

Fixtures actuales deben mantener resultados semánticos antes/después.
