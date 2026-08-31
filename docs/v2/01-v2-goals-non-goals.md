# Goals y Non-Goals V2

## Goals

1. Architecture World persistente.
2. Event sourcing auditable.
3. Arquitectura forkable para hipótesis.
4. Code facts separados del razonamiento.
5. Context Compiler para minimizar contexto LLM.
6. Behaviors reactivos.
7. LikeC4/Arrows como proyecciones.
8. Architecture drift.
9. Menos file reads/tool calls/tokens.
10. Mantener instalación global y repositorio fuente read-only.

## Non-Goals iniciales

No construir:

- parser propio;
- compiler frontend;
- graph DB server;
- UI;
- SaaS;
- distributed index;
- vector DB obligatorio;
- full CPG;
- componentes propios en otros lenguajes para optimización prematura;
- CodeQL obligatorio;
- runtime telemetry obligatorio.

## Deferred

- SCIP obligatorio;
- co-change;
- test impact;
- runtime overlay;
- organization graph.
