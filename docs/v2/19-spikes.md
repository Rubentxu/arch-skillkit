# Spikes V2

## SPIKE-01 ActiveGraph fit

1 repo, observations, claims, decision, contradiction, replay.

## SPIKE-02 SQLite Code Index

100k symbols / 500k edges.
Medir ingest, p50/p95, DB size.

## SPIKE-03 Context Compiler

Agent-only vs ContextPack.
Medir reads, calls, tokens, correctness.

## SPIKE-04 SCIP

Rust + Kotlin + TypeScript.
Comparar scanners base vs +SCIP.

## SPIKE-05 Fork/diff

Scenario sync payment → async payment.

## SPIKE-06 Python performance

Ejecutar sólo si aparece un cuello de botella medido.

Evaluar en este orden:

- SQLite schema/indexes;
- batch ingest;
- incremental processing;
- cache;
- multiprocessing;
- backend existente alternativo.

El spike no contempla una reimplementación propia en Go.
