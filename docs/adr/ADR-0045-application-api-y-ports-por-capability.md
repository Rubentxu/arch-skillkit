# ADR-0045 — Application API y ports por capability

Status: Proposed

## Contexto

`ArchitectureWorldPort` amplio y delivery code que construye concretos crecerán con status, MCP y Control Plane.

## Decisión

Introducir Application API con use cases y separar ports en grupos cohesionados:

- ArchitectureQueryPort;
- EvidenceQueryPort;
- CodeGraphQueryPort;
- ArchitectureMutationPort;
- GovernancePort;
- HistoryQueryPort;
- ProjectionPort;
- ViewerPort.

No crear una interfaz por método. El criterio es capability/lifecycle y sustitución real.

## Migración

Strangler incremental: nuevos use cases usan nuevos ports; legacy se migra sin big-bang.
