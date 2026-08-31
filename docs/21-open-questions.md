# Open Questions

No bloquean V1 salvo indicación.

## OQ-01 — Nombre público

`ArchSkillKit` es nombre de trabajo.

Antes de v0.1 pública:

- revisar disponibilidad GitHub;
- naming;
- identidad visual mínima.

## OQ-02 — Registry identity

¿Remote tiene prioridad suficiente para clones múltiples?

Resolver con UAT.

## OQ-03 — Model update strategy

¿Agente edita LikeC4 existente o regenera secciones gestionadas?

Preferencia inicial: edición conservadora.

## OQ-04 — Evidence references en LikeC4

Definir convención concreta de metadata/links según capacidades exactas del DSL usado.

## OQ-05 — Arrows generation

Definir schema mínimo estable y naming de views.

## OQ-06 — Semgrep licensing/modes

Mantener V1 compatible con Semgrep CE para core.

Capacidades propietarias sólo opcionales.

## OQ-07 — SCIP

Decidir tras Phase 7.

## OQ-08 — Shell vs tiny executable

Mantener shell mientras sea trivial.

Migrar sólo si portabilidad/lógica lo exige.

## OQ-09 — macOS/Windows

V1 prioriza Linux/XDG.

Diseñar abstracción de paths compatible con macOS; Windows se evalúa después.

## OQ-10 — Workspace versioning

¿Permitir inicializar Git automáticamente?

Preferencia: nunca por defecto. Acción explícita.
