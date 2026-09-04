# ArchSkillKit V2.5 — Architecture Integrity & Intelligence Kernel

Este paquete es una evolución **mergeable** sobre la línea V2.4 actual de
ArchSkillKit. No propone un rewrite. Su objetivo es cerrar la distancia entre la
arquitectura conceptual del proyecto y la arquitectura física del código, y
hacer que esa alineación sea **medible, reproducible y determinista**.

> V2.5 es una línea de diseño/evolución. No implica por sí sola un número
> SemVer del paquete Python.

## Qué añade

1. Especificación refinada del Architecture Intelligence Kernel.
2. Application API y Composition Root como frontera única para CLI/MCP/HTTP.
3. Eliminación progresiva de `delivery -> delivery`.
4. Anti-corruption boundary real frente a ActiveGraph.
5. `CodeGraphQueryPort` y proveedores de inteligencia de código.
6. `ArchitectureDelta` como concepto first-class.
7. Modelo de extensibilidad limitado y explícito.
8. Learning Architecture: inferencia repetida -> SensorCandidate -> sensor determinista.
9. Contratos de arquitectura verificables.
10. Gates de calidad con IDs estables.
11. Estrategia de tests de invariantes y propiedades.
12. Roadmap por milestones con entry/exit criteria.
13. Plan UAT trazable y versionado.
14. Migración tipo strangler, sin big bang.
15. Un verificador AST de stdlib que puede incorporarse inmediatamente a CI.

## Estructura

- `docs/v2/70-*` a `87-*`: especificaciones, roadmap, UAT y migración.
- `docs/v2/adr/ADR-0046-*` a `ADR-0056-*`: decisiones arquitectónicas.
- `verification/architecture-contracts.json`: contratos ejecutables.
- `verification/architecture-baseline.example.json`: baseline inicial de deuda.
- `verification/arch_conformance.py`: verificador determinista.
- `verification/quality-gates.json`: catálogo estable de gates.
- `verification/traceability.json`: requirement -> ADR -> gate -> test -> UAT.
- `verification/uat-v2.5-plan.json`: catálogo UAT machine-readable.
- `verification/metrics.schema.json`: contrato de métricas.
- `verification/README.md`: integración y política de uso.

## Política de adopción

La arquitectura objetivo NO se introduce con un refactor masivo.

Se adopta con:

`measure -> baseline -> prevent regression -> migrate slice -> reduce baseline -> gate hard`

Un baseline sólo sirve para reconocer deuda existente. Nunca autoriza deuda nueva.
El baseline debe reducirse monotónicamente y cualquier incremento requiere ADR o
waiver explícito y temporal.

## Orden recomendado

1. Integrar `verification/`.
2. Ejecutar el verificador contra `main` y generar/revisar baseline.
3. Añadir los gates como informativos.
4. Migrar Proposal/Governance Application API.
5. Hacer hard el gate `delivery_to_delivery`.
6. Introducir Composition Root.
7. Encapsular ActiveGraph.
8. Introducir CodeGraphQueryPort.
9. Hacer hard todos los boundaries.
10. Implementar ArchitectureDelta.
11. Continuar con Change Intelligence, Agent Context y Learning Architecture.
