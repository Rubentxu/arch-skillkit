# VisualIntent Specification

## Objetivo

Evitar que agentes y dominio estén acoplados a nombres de herramientas.

El agente debe expresar intención semántica.

## Modelo

```yaml
type: dependency_graph
subject: orders
scope:
  depth: 3
audience: engineer
interaction: exploratory
detail: medium
```

## Tipos iniciales

### architecture

Destino preferido: LikeC4.

### exploration

Destino preferido: Arrows.

### technical_diagram

Destino preferido: draw.io.

### knowledge_map

Destino preferido: JSON Canvas.

### dependency_graph

Destino preferido: GraphML.

### large_graph_analysis

Destino preferido: GraphML.

### proposal_board

Destino preferido: JSON Canvas o draw.io.

### investigation

Destino preferido: JSON Canvas / Arrows según granularidad.

## Attributes

```text
type
subject
scope
audience
interaction
detail
editable
layout_hint
include_evidence
include_notes
```

## Selection rules

### LikeC4

Si el objetivo principal es:

- C4;
- architecture views;
- system/container/component;
- deployment.

### Arrows

Si:

- grafo curado;
- propiedades;
- relación explícita;
- edición exploratoria.

### draw.io

Si:

- diagrama técnico general;
- layout libre;
- UML-like;
- infra/cloud;
- propuesta visual editable.

### JSON Canvas

Si:

- mapa mental;
- notas conectadas;
- investigation board;
- knowledge map;
- contexto conceptual.

### GraphML

Si:

- grafo grande;
- análisis;
- clustering;
- centralidad;
- layout avanzado;
- consumer-neutral graph exchange.
