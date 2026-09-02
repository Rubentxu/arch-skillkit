# ADR-0041 — AgentSession como lease explícito de contexto versionado

Status: Proposed

## Contexto

Agentes largos pueden actuar con arquitectura stale. MCP 2026-07-28 no ofrece sesión implícita que deba usarse como estado de aplicación.

## Decisión

Crear `AgentSession` con snapshot/world/code/policy revisions, scope y budget.

Si cambia una revision material:

- la sesión se marca stale;
- operaciones sensibles devuelven warning/error estable;
- el agente refresca ContextPack.
