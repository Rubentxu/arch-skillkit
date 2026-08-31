# ADR-0003: Agent Skills como unidad principal de distribución

- Status: Accepted
- Date: 2026-08-31

## Context

La solución debe compartirse públicamente y ser portable entre varios agentes sin instalar recursos en cada repo.

## Decision

Usar el estándar Agent Skills como formato canónico. GitHub Skills/skills.sh serán canales, no formatos propietarios del proyecto.

## Consequences

### Positive

- Portabilidad.
- Distribución global.
- Git-native.
- Fácil inspección.

### Negative / Trade-offs

- Diferencias entre agentes.
- Algunas capacidades pueden requerir fallback.

## Revisit when

Si el ecosistema converge en otro estándar ampliamente adoptado.
