# ADR-0051 — Deterministic Architecture Conformance

Status: Accepted

## Verification evidence

`docs/v2/verification/arch_conformance.py:18` — `Finding` dataclass drives the deterministic conformance gate; findings are stable across runs for identical source tree and contracts.

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
