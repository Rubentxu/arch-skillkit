# ADR-0039 — MCP como delivery adapter opcional y read-only por defecto

Status: Proposed

## Contexto

MCP distribuye capacidades a coding agents, pero no debe convertirse en el domain API ni conceder mutaciones peligrosas por defecto. La spec objetivo 2026-07-28 usa core stateless.

## Decisión

- SDK MCP como extra opcional;
- Application API debajo;
- handles explícitos (`session_id`, `snapshot_id`, etc.);
- capability tiers READ / PROPOSE / ADMIN;
- READ default;
- promotion/waivers ADMIN disabled por defecto.

## Consecuencia

No depender de sampling/session implícita del protocolo para la lógica del producto.
