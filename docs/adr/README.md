# Architecture Decision Records

## Estados

- Proposed
- Accepted
- Superseded
- Rejected

## Regla

No editar retrospectivamente una decisión significativa.

Si cambia:

1. crear nuevo ADR;
2. marcar el anterior como Superseded;
3. enlazar ambos.

## ADRs iniciales

- ADR-0001 Repository read-only
- ADR-0002 XDG workspace
- ADR-0003 Agent Skills
- ADR-0004 Tool-first / no backend
- ADR-0005 LikeC4 canonical model — **Superseded by ADR-0015 and ADR-0016** (sigue siendo baseline de V1)
- ADR-0006 Arrows projection
- ADR-0007 ast-grep + Semgrep
- ADR-0008 Evidence First
- ADR-0009 mise
- ADR-0010 Thin glue
- ADR-0011 SCIP/CodeQL deferred
- ADR-0012 Emergent architecture triggers

## ADRs V2 (ActiveGraph evolution)

- ADR-0013 Python + ActiveGraph como runtime V2
- ADR-0014 Evidence Graph y Architecture World separados
- ADR-0015 ActiveGraph Event Log como source of truth
- ADR-0016 LikeC4 pasa a ser proyección
- ADR-0017 Arrows continúa como proyección exploratoria
- ADR-0018 SQLite como code index inicial
- ADR-0019 SCIP opcional y medido
- ADR-0020 Context Compiler como capability central
- ADR-0021 Fork/diff para propuestas arquitectónicas
- ADR-0022 Drift determinista antes que LLM
- ADR-0023 Go deferido como accelerator — **Rejected** (resuelta por ADR-0025)
- ADR-0024 Encapsular ActiveGraph detrás del dominio
- ADR-0025 Python + ActiveGraph fijado como stack propio

### ADRs V2.2 (projection applications)

- ADR-0026 VisualIntent y Projection Router
- ADR-0027 draw.io como proyección técnica general
- ADR-0028 JSON Canvas para mapas de conocimiento
- ADR-0029 GraphML como formato de intercambio de grafos
- ADR-0030 Proyecciones unidireccionales en V2.2
- ADR-0031 No construir UI propia para visualización

### ADRs V2.4 (architecture intelligence & agent governance)

- ADR-0032 Architecture Intelligence Core como producto
- ADR-0033 ArchitectureSnapshot, RunLedger y RuntimeRegistry separados
- ADR-0034 Projection Format y Viewer Application separados
- ADR-0035 Control Plane como orquestador, no renderer (clarifica ADR-0031)
- ADR-0036 Graph-native semantics con persistencia especializada
- ADR-0037 LLM produce Candidate Knowledge, no Accepted Architecture
- ADR-0038 Prompts/Skills/Revisions versionadas y hashadas
- ADR-0039 MCP delivery adapter opcional, read-only por defecto
- ADR-0040 Fitness Profile antes que score compuesto
- ADR-0041 AgentSession como version lease
- ADR-0042 Sensor distillation desde inferencias LLM repetibles
- ADR-0043 Semantic State separado de Presentation State
- ADR-0044 Snapshot attestation reutiliza Sigstore
- ADR-0045 Application API y ports por capability

La especificación V2 completa vive en `docs/v2/` (núcleo V2.1 en docs
00–23, capa de proyecciones V2.2 en docs 24–43, evolutivo V2.4 en docs
49–69); la V1 se conserva como baseline/bootstrap y no se reescribe.
