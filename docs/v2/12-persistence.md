# Persistencia

```text
$XDG_DATA_HOME/arch-skillkit/projects/<project-id>/
├── project.json
├── code.sqlite
├── activegraph.sqlite
├── evidence/
├── likec4/
├── arrows/
├── reports/
└── exports/
```

## code.sqlite

Regenerable.

## activegraph.sqlite

Durable source of truth.

Necesita:

- backup;
- schema version;
- migrations;
- lineage.

## Raw evidence

Retención configurable.

## External GraphStore

No introducir FalkorDB u otro backend antes de benchmark.
