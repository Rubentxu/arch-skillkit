# Arquitectura V2

```text
GLOBAL INSTALLATION
      │
      ▼
Python package
      │
ActiveGraph runtime
      │
 ┌────┼─────┐
 ▼    ▼     ▼
Packs Behaviors Skills
      │
      ▼
PROJECT WORKSPACE
 ┌───────────────┬──────────────────┐
 ▼               ▼                  ▼
code.sqlite  activegraph.sqlite   evidence/
regenerable  source of truth        raw
 └───────────────┬──────────────────┘
                 ▼
          Context Compiler
                 ▼
               Agents
          ┌──────┴──────┐
          ▼             ▼
       LikeC4          Arrows
```

## Hexagonal boundary

Scanners, projections y source adapters no importan tipos ActiveGraph.

ActiveGraph queda encapsulado detrás del dominio ArchSkillKit.

## External adapters

- ast-grep;
- Semgrep;
- SCIP;
- Git;
- build metadata;
- LikeC4;
- Arrows.
