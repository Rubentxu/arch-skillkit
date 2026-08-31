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

La especificación V2 completa vive en `docs/v2/`; la V1 se conserva como
baseline/bootstrap y no se reescribe.
