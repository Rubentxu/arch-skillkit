# ADR-0048 — ActiveGraph Anti-Corruption Boundary

Status: Proposed

## Context

El proyecto es ActiveGraph-first, pero repositorios y servicios conocen
`world.graph` y la estructura del engine.

## Decision

Conservar ActiveGraph como implementación estratégica del Architecture World,
pero confinar su API concreta a outbound adapter/ACL. Domain/Application usan
contratos del proyecto.

## Consequences

No ocultar event sourcing/forks como conceptos; sí ocultar `Graph`, `Runtime`,
store URLs y object shapes.

## Verification

`ARCH-ACTIVEGRAPH-001`, `ARCH-GRAPH-LEAK-001`, UAT25-030/031/032.
