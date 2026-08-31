# ADR-0025: Fijar Python + ActiveGraph como stack propio

- Status: Accepted
- Date: 2026-08-31

## Context

Durante el diseño V2 se mantuvo abierta la posibilidad de introducir componentes propios en Go si aparecían problemas de rendimiento o distribución.

Esa apertura introduce una bifurcación tecnológica innecesaria y contradice el objetivo de mantener una solución cohesionada, pequeña y orientada a reutilizar herramientas existentes.

## Decision

La capa propia de ArchSkillKit permanecerá en **Python + ActiveGraph**.

No se contempla:

- Go accelerator;
- Go indexer;
- CLI propio en Go;
- daemon propio en Go;
- migración parcial o total a Go;
- benchmarks cuyo objetivo sea justificar una reimplementación en Go.

Cuando aparezcan problemas de rendimiento se resolverán mediante:

- optimización Python;
- mejor diseño de datos;
- SQLite tuning;
- incrementalidad;
- batching;
- caching;
- multiprocessing;
- backends existentes;
- herramientas externas especializadas.

## Consequences

### Positive

- un único stack propio;
- menor complejidad operativa;
- menor carga cognitiva;
- integración natural con ActiveGraph;
- releases y debugging más sencillos;
- arquitectura emergente más enfocada.

### Negative / Trade-offs

- se renuncia deliberadamente a optimizaciones mediante un segundo lenguaje propio;
- algunos hot paths podrían depender más de herramientas externas o backends especializados.

## Supersedes / Resolves

- Rechaza la línea futura propuesta en ADR-0023.

## Revisit when

No existe un trigger tecnológico previsto para reabrir Go.

Una eventual reconsideración requeriría un cambio explícito de estrategia de producto, no un simple benchmark de rendimiento.
