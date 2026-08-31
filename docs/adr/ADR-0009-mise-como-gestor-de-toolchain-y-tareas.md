# ADR-0009: mise como gestor de toolchain y tareas

- Status: Accepted
- Date: 2026-08-31

## Context

No queremos Just + gestores separados + configs dentro de repositorios.

## Decision

Usar mise para versiones y tareas, con configuración alojada en ArchSkillKit.

## Consequences

### Positive

- Menos dependencias conceptuales.
- Toolchain reproducible.
- Config externa.

### Negative / Trade-offs

- Dependencia operativa en mise.
- Algunos tools pueden necesitar instalación especial.

## Revisit when

Si mise no puede gestionar de forma fiable una parte crítica del toolchain.
