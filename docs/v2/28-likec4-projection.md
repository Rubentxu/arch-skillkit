# LikeC4 Projection

## Purpose

Arquitectura normativa y navegable.

## Inputs

- accepted ArchitectureElements;
- accepted ArchitectureRelations;
- decisions;
- confidence;
- evidence metadata where useful.

## Output

```text
likec4/
  model.c4
  views/
```

## Non-goals

No incluir:

- full Code Graph;
- raw scanner findings;
- every symbol;
- temporary investigation notes.

## Update strategy

Conservative regeneration.

Declared/manual architecture decisions must survive reruns.

## Role in V2.2

LikeC4 remains the primary architecture application, but no longer the only visual destination.
