# ADR-0046 — Canonical Application API and Composition Root

Status: Proposed

## Context

CLI, MCP y HTTP han crecido con wiring y reutilización entre adapters. Esto
produce connascence de execution/format y dificulta parity.

## Decision

Introducir un Application API canonical y un Composition Root por repo.
Inbound adapters sólo parsean/renderizan. Toda semántica vive en use cases.

## Consequences

Positive:
- elimina delivery chaining;
- permite parity;
- centraliza lifecycle;
- facilita tests.

Negative:
- DTOs/commands adicionales;
- migración gradual.

## Verification

- ARC-001/002/004/005;
- UAT25-020/022;
- application API coverage.
