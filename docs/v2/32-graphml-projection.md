# GraphML Projection

## Purpose

Formato universal para grafos medianos/grandes y análisis interactivo externo.

## Consumers

### Cytoscape

Best for:

- interactive network exploration;
- filtering;
- attribute-driven styling;
- network analysis.

### Gephi

Best for:

- very large graphs;
- communities;
- centrality;
- modularity;
- temporal networks.

### yEd

Best for:

- high-quality automatic layouts;
- editable dependency diagrams;
- hierarchical/orthogonal views.

## Output

```text
graphml/
  code-dependencies.graphml
  architecture-evidence.graphml
  co-change.graphml
  impact.graphml
```

## Node attributes

Possible:

- id;
- label;
- type;
- language;
- module;
- file;
- architecture_layer;
- confidence;
- origin;
- churn;
- centrality (future);
- bounded_context.

## Edge attributes

- kind;
- origin;
- confidence;
- evidence_count;
- first_seen;
- last_seen.

## Rule

GraphML should be consumer-neutral.

Do not encode Cytoscape/Gephi/yEd-specific semantics unless via optional extension profiles.
