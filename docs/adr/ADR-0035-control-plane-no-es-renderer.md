# ADR-0035 — Control Plane como orquestador, no renderer

Status: Proposed
Supersedes/clarifies: ADR-0031

## Contexto

V2.4 necesita una UI local para evidencia, history, governance y viewer integration, pero ADR-0031 evita construir un visualizador propio.

## Decisión

El Control Plane puede existir si actúa como shell/orchestrator y reutiliza visualizadores existentes.

Permitido:

- LikeC4 Web Component/serve;
- draw.io embed;
- Excalidraw component si se acepta;
- launch/handoff a yEd, Gephi, Obsidian, VS Code, etc.;
- evidence/governance panels propios.

No permitido:

- implementar un engine general de layout/render graph;
- convertir una UI propietaria en formato canónico.
