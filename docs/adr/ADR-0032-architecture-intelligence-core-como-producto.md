# ADR-0032 — Architecture Intelligence Core como producto

Status: Proposed

## Contexto

El documento 48 proponía “CLI is the product”. Con status, MCP, Control Plane, agents y viewer adapters, hacer del CLI el centro introduciría connascence entre delivery y dominio y haría que MCP/HTTP acabasen ejecutando CLI/subprocesses.

## Decisión

El producto arquitectónico es el **Architecture Intelligence Core**. CLI, MCP y HTTP son delivery adapters equivalentes sobre Application API.

El CLI permanece:

- UX de referencia;
- superficie estable de scripting;
- mecanismo de troubleshooting;
- fallback cuando no existe integración richer.

## Consecuencias

Positivas:

- contracts reutilizables;
- testabilidad;
- MCP/control plane no duplican lógica;
- evita CLI God Object.

Coste:

- requiere introducir Application API/use cases y DTOs antes de features de producto grandes.
