# draw.io Projection

## Purpose

Proporcionar un destino universal para diagramas técnicos editables.

## Use cases

- deployment diagrams;
- infrastructure;
- cloud architecture;
- domain diagrams;
- technical flows;
- proposal diagrams;
- security boundaries;
- mixed diagrams not naturally expressible in C4.

## Output

```text
drawio/
  architecture-overview.drawio
  deployment.drawio
  security-boundaries.drawio
  proposal-<id>.drawio
```

## Design principle

El projector debe generar un layout razonable, no perfecto.

El valor de draw.io es que el usuario puede:

- mover;
- reagrupar;
- anotar;
- enriquecer;
- exportar.

## Graph source

Preferir:

- Architecture World;
- Proposal;
- curated ContextPack.

No generar draw.io directamente desde millones de Code Graph edges.

## Layout

V2.2:

- basic deterministic layout;
- groups/swimlanes when known;
- stable IDs.

Advanced layout remains external/manual.
