# ADR-0048 — ActiveGraph Anti-Corruption Boundary

Status: Accepted

## Verification evidence

`ArchitectureWorldPort` at `python/src/archskillkit/ports.py:17` and `ArchitectureQueryPort` at `python/src/archskillkit/application/ports/architecture_query.py:13` formalize the domain surface with concrete ActiveGraph confined behind the port boundary.

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
