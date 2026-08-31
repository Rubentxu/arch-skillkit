# Roadmap V2

## Phase A — ActiveGraph foundation

### M2-A1 Python package

### M2-A2 Domain ontology

### M2-A3 Event persistence/replay

Exit: estado actual reconstruible desde event log.

## Phase B — Code Index

### M2-B1 SQLite schema

### M2-B2 ast-grep ingestion

### M2-B3 Semgrep ingestion

### M2-B4 query API

Exit: agentes obtienen facts sin leer source.

## Phase C — Evidence → Architecture

### M2-C1 Observation ingestion

### M2-C2 Claim lifecycle

### M2-C3 Architecture mapper

### M2-C4 Reviewer

## Phase D — Context Compiler

### M2-D1 ContextPack

### M2-D2 budgeted queries

### M2-D3 snippets

### M2-D4 context-read metrics

Target: >= 50% menos source reads vs agent-only.

## Phase E — Projections

### M2-E1 LikeC4 projector

### M2-E2 Arrows projector

### M2-E3 consistency review

## Phase F — Reactive Architecture

### M2-F1 drift

### M2-F2 contradiction

### M2-F3 stale model

## Phase G — Fork/Diff

### M2-G1 proposal

### M2-G2 fork

### M2-G3 structural diff

### M2-G4 promote/reject

## Phase H — SCIP spike

Adopt / optional / reject.

## Phase I — Performance & architecture checkpoint

Evaluar:

- rendimiento Python;
- SQLite scale;
- latencia del Context Compiler;
- memoria;
- instalación;
- necesidad de incrementalidad;
- necesidad de un backend existente alternativo.

La capa propia permanece Python + ActiveGraph.

## Releases

- v0.5 ActiveGraph foundation
- v0.6 Code Index
- v0.7 Context Compiler + projections
- v0.8 Drift + review
- v0.9 Fork/diff + SCIP spike
- v1.0 Stable V2 contracts
