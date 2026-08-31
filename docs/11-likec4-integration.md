# Integración LikeC4

## Papel

LikeC4 es la representación arquitectónica canónica de V1.

## Por qué

- DSL textual;
- versionable;
- orientado a arquitectura;
- múltiples views;
- apto para agentes;
- validación mecánica;
- integración MCP/Skills disponible.

## Scope

LikeC4 debe contener arquitectura, no cada detalle del AST.

### Recomendado

- systems;
- containers;
- componentes relevantes;
- external systems;
- datastores;
- queues/topics;
- relaciones significativas;
- deployment cuando se conozca.

### Evitar

- cada función;
- cada clase;
- cada import;
- todo el call graph.

Eso pertenece a evidence/Arrows.

## Metadata recomendada

Cuando sea viable:

```text
origin = detected | inferred | declared
confidence = high | medium | low
evidence = referencia corta
```

## Views iniciales

Cada proyecto debería intentar producir:

1. `context`
2. `containers`
3. `dependencies`
4. `external-integrations`
5. `data-stores`
6. `messaging` si aplica
7. `architecture-review` si hay findings

## Validación

El pipeline debe considerar fallo si el LikeC4 generado no parsea/valida.

## Model lifecycle

El modelo no se regenera destructivamente por defecto.

El agente debe:

- conservar declaraciones humanas;
- actualizar findings;
- marcar obsolescencia;
- evitar borrar decisiones sin evidencia.
