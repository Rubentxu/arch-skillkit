# ADR-0044 — Architecture Snapshot attestations reutilizan Sigstore

Status: Proposed

## Contexto

El proyecto ya usa attestation Sigstore en distribución. Snapshots verificables pueden beneficiar CI/enterprise, pero crear firma propia añade riesgo.

## Decisión

Cuando M3/S24-11 demuestre valor, `ark attest` firma/manifiesta snapshot + evidence/policy/tool revisions usando mecanismos Sigstore existentes.

No firmar cada nodo/evento individualmente en V2.4.
