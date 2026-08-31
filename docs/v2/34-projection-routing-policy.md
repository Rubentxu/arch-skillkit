# Projection Routing Policy

## Rules

### Route to LikeC4 when

- request is architecture-first;
- C4 level matters;
- navigation across architecture views matters.

### Route to Arrows when

- selected graph is small/medium;
- user wants property editing;
- exploration is primary.

### Route to draw.io when

- representation is heterogeneous;
- visual composition matters;
- user likely wants manual refinement.

### Route to JSON Canvas when

- knowledge/notes/context matter;
- mindmap or investigation board requested;
- file/document links are useful.

### Route to GraphML when

- graph is medium/large;
- analysis/layout tool should be chosen externally;
- graph statistics/community analysis may matter.

## Thresholds

Initial recommendations, configurable:

```text
Arrows:
  <= 500 nodes
  <= 2,000 edges

JSON Canvas:
  <= 300 visual cards

draw.io:
  <= 500 visual elements

GraphML:
  no artificial low threshold
```

These are UX defaults, not engine limits.

## Multi-projection

One intent may produce multiple outputs if they answer different questions.

Example:

```text
architecture review
  -> LikeC4
  -> findings.canvas
  -> dependency.graphml
```

Do not generate multiple formats by default without clear value.
