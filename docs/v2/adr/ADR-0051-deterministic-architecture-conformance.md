# ADR-0051 — Deterministic Architecture Conformance

Status: Proposed

## Decision

La arquitectura física se valida con contratos AST/import deterministas y
baseline exacto versionado.

## Policy

- no-new-debt desde M0;
- baseline monotónicamente descendente;
- hard gate al llegar a cero;
- waiver excepcional con expiry.

## Verification

`verification/arch_conformance.py`.
