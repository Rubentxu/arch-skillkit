# Roadmap V2.2

Las especificaciones del bundle `arch-skillkit-v2.2-projection-applications/` ya fueron absorbidas en los documentos canónicos `docs/v2/24`–`43`. El bundle es histórico y no se gestiona como segunda fuente. Estado global: [`STATUS.md`](STATUS.md).

| Workstream | Estado actual | Exit restante |
|---|---|---|
| P0 — Projection foundation | Implemented; local suite green | UAT |
| P1 — LikeC4/Arrows normalization | Implemented; local suite green | UAT |
| P2 — JSON Canvas | Pending | writer + fixtures + UAT |
| P3 — GraphML | Pending | writer + compatibilidad + UAT |
| P4 — draw.io | Pending | writer + IDs estables + UAT |
| P5 — Routing | Partial | thresholds y política productiva |
| P6 — Lifecycle | Partial | cerrar redacción y validación integrada |
| P7 — Real-world validation | Pending | tres stacks y consumidores externos |
| P8 — Projection checkpoint | Pending | métricas de uso de P2–P7 |

La ejecución comienza después del gate V2.1 y cierra un slice antes de abrir el siguiente.

## Phase P0 — Projection foundation

### P0.1 VisualIntent schema

### P0.2 ProjectionAdapter protocol

### P0.3 Projection metadata/lifecycle

Exit:

- one intent can be routed deterministically.

## Phase P1 — Existing projections normalization

### P1.1 LikeC4 adapter

### P1.2 Arrows adapter

Exit:

- both conform to common ProjectionResult.

## Phase P2 — JSON Canvas

### P2.1 schema writer

### P2.2 knowledge map

### P2.3 investigation board

Exit:

- valid `.canvas` opens in Obsidian/compatible consumer.

## Phase P3 — GraphML

### P3.1 generic exporter

### P3.2 Code Index subgraph export

### P3.3 Architecture/Evidence overlay export

Exit:

- same file opens in Cytoscape, Gephi and yEd.

## Phase P4 — draw.io

### P4.1 basic XML generation

### P4.2 stable IDs

### P4.3 group/lane projection

### P4.4 proposal diagram

Exit:

- valid editable `.drawio`.

## Phase P5 — Routing

### P5.1 rule-based router

### P5.2 size thresholds

### P5.3 user override

Exit:

- intents route predictably.

## Phase P6 — Projection lifecycle

### P6.1 source revision

### P6.2 stale detection

### P6.3 manual-edit protection

## Phase P7 — Real-world validation

Repositories:

- Rust
- Kotlin/Java
- TypeScript

Applications:

- LikeC4
- Arrows
- draw.io
- Obsidian Canvas
- Cytoscape
- Gephi
- yEd

## Phase P8 — Projection checkpoint

Decide based on usage:

- keep/remove applications;
- add profiles;
- consider bidirectional import;
- consider new formats only with unmet intent.

## Orden de entrega

1. JSON Canvas.
2. GraphML.
3. draw.io.
4. Redacción productiva.
5. Thresholds/routing productivo.
6. Validación real y checkpoint.

El orden de P2–P4 puede cambiar si el checkpoint V2.1 aporta evidencia de mayor valor para otro consumidor.
