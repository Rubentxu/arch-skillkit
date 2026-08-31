# Arrows Projection

## Purpose

Exploración manual de un property graph curado.

## Best suited for

- ports/adapters;
- selected dependencies;
- evidence trails;
- domain relations;
- architectural investigations.

## Output

```text
arrows/
  overview.arrows
  investigation-*.arrows
  findings-*.arrows
```

## Scope guard

Avoid dumping the complete Code Index into Arrows.

If node/edge volume exceeds the exploration threshold, route to GraphML.
