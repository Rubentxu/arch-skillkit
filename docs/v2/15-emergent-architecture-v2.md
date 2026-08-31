# Arquitectura emergente V2

## SCIP

Trigger: targeted source reads altos por resolución cross-file deficiente.

## Incremental Code Index

Trigger: full scan demasiado lento.

Usar Git diff + hashes.

## Co-change

Trigger: necesidad de coupling histórico.

## Test impact

Trigger: workflow de selección de tests aporta valor.

## Runtime overlay

Trigger: comparar arquitectura detectada con tráfico observado.

## CodeQL

Trigger: dataflow/security reales.

## External GraphStore

Trigger: materialized graph insuficiente.

## Python performance evolution

Trigger: benchmarks muestran un cuello de botella real.

Orden de actuación:

1. query/schema optimization;
2. batching;
3. incremental indexing;
4. caching;
5. multiprocessing;
6. backend existente alternativo.

No se contempla una implementación propia en Go.

## Organization Graph

Trigger: consultas multi-repo repetidas.

## UI

Trigger: LikeC4 + Arrows + reports no resuelven workflows.

## Complexity gate

Toda complejidad necesita:

1. dolor medido;
2. spike;
3. ADR;
4. UAT;
5. rollback.
