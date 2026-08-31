# Migración V1 → V2

## Preserved

- repository-clean;
- XDG;
- global install;
- Agent Skills;
- mise;
- ast-grep;
- Semgrep;
- LikeC4;
- Arrows;
- evidence-first;
- emergent architecture.

## Changed

### LikeC4

V1 canonical model → V2 projection.

### Code

V1 thin glue → V2 permite Python domain code para:

- ontology;
- ingestion;
- context compiler;
- projection coordination.

Scanners siguen externos.

### Lenguaje de la capa propia

Python + ActiveGraph queda fijado como stack de la capa propia.

No se mantiene una línea futura de implementación en Go.

## Import existing V1 workspace

Importar evidence/model mediante eventos explícitos de bootstrap.

No falsificar historia previa.
