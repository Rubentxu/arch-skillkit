# ADR-0005: LikeC4 como modelo arquitectónico canónico de V1

- Status: Superseded by ADR-0015 and ADR-0016 (V2)
- Date: 2026-08-31

> V2 desplaza a LikeC4 de modelo canónico a proyección: el EventStore de
> ActiveGraph pasa a ser la fuente de verdad arquitectónica y LikeC4 se
> regenera desde Architecture World. Esta decisión sigue siendo el baseline
> válido de la pipeline V1 (ver `docs/17-roadmap.md`).

## Context

Se necesita una representación textual, versionable, validable y adecuada para arquitectura.

## Decision

LikeC4 será el source of truth arquitectónico de V1. La evidencia raw no desaparece y sigue siendo fuente de provenance.

## Consequences

### Positive

- Evita IR propio.
- Modelado C4 y views.
- Buen encaje con agentes.

### Negative / Trade-offs

- No representa todo el detalle del code graph.
- Acoplamiento conceptual a su DSL durante V1.

## Revisit when

Si las consultas exceden de forma recurrente sus capacidades o aparece necesidad de grafo canónico más rico.
