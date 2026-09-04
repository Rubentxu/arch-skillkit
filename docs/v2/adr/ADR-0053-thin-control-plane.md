# ADR-0053 — Thin Local Control Plane

Status: Accepted

## Verification evidence

`python/src/archskillkit/delivery/cli/control_plane.py:2628` — Control Plane HTTP handlers are limited to transport, auth, mapping and static UI; domain semantics are handled by the application layer.

## Decision

Control Plane conserva HTTP/UI local pero pierde semántica de dominio.
Responsabilidades limitadas a transport, auth, mapping y static UI.

## Rejected

Adoptar un framework web como solución primaria al acoplamiento.

## Verification

Architecture gates + parity + local security UAT.
