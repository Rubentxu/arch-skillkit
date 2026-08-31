# Reglas de evolución de visualizadores

## Add a new application only if

1. cubre un VisualIntent no satisfecho;
2. aporta interacción/edición/análisis distinto;
3. tiene formato file-based razonable;
4. no requiere backend propio;
5. puede mantenerse como adapter aislado.

## Reject if

- sólo cambia estética;
- duplica LikeC4/Arrows/draw.io/Canvas/GraphML;
- requiere integración cloud obligatoria;
- obliga a introducir UI propia;
- no tiene formato estable/documentable.

## Preferred hierarchy

1. standard exchange format;
2. open application-specific format;
3. application API;
4. custom integration.

## Example

Prefer:

```text
GraphML -> Cytoscape / Gephi / yEd
```

over:

```text
CytoscapeAdapter
GephiAdapter
yEdAdapter
```

This minimizes coupling.
