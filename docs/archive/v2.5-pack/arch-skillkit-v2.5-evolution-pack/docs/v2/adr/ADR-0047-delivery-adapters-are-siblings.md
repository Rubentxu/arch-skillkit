# ADR-0047 — Delivery Adapters Are Siblings

Status: Proposed

## Context

MCP/HTTP reutilizan handlers CLI mediante namespaces sintéticos y captura de
stdout.

## Decision

Ningún inbound adapter puede usar otro inbound adapter como API.

## Rejected

- conservar stdout JSON como IPC in-process;
- compartir `argparse.Namespace`.

## Verification

`ARCH-DELIVERY-001` y UAT25-013/014.
