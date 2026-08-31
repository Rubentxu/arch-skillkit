# JSON Canvas Projection

## Purpose

Mapas mentales, knowledge maps e investigation workspaces.

## Output

```text
canvas/
  system.canvas
  bounded-context-orders.canvas
  investigation-<id>.canvas
  proposal-<id>.canvas
```

## Node types

Preferir:

- text;
- file;
- link;
- group.

## Best practices

### Use Markdown text cards

Para:

- summaries;
- decisions;
- findings;
- assumptions.

### Use file nodes

Para:

- reports;
- ADRs;
- evidence notes;
- generated docs.

### Use groups

Para:

- bounded contexts;
- systems;
- containers;
- investigation clusters.

### Use labeled edges

Para:

- depends_on;
- supports;
- contradicts;
- realizes;
- evidenced_by.

## Why JSON Canvas

Formato simple, abierto y fácil de generar.

Obsidian es un consumidor recomendado, pero ArchSkillKit no depende de Obsidian.
