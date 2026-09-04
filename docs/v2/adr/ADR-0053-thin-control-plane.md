# ADR-0053 — Thin Local Control Plane

Status: Proposed

## Decision

Control Plane conserva HTTP/UI local pero pierde semántica de dominio.
Responsabilidades limitadas a transport, auth, mapping y static UI.

## Rejected

Adoptar un framework web como solución primaria al acoplamiento.

## Verification

Architecture gates + parity + local security UAT.
