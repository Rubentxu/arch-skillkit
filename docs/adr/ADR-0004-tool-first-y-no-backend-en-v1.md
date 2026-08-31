# ADR-0004: Tool-first y no backend en V1

- Status: Accepted
- Date: 2026-08-31

## Context

ast-grep, Semgrep, LikeC4 y metadata de build ya resuelven grandes partes del problema.

## Decision

V1 no tendrá backend, DB, daemon ni parser propio. Orquestará herramientas existentes mediante Skill, mise y thin glue.

## Consequences

### Positive

- Menor mantenimiento.
- Time-to-value rápido.
- Fácil reemplazo de herramientas.

### Negative / Trade-offs

- Menos control interno.
- Outputs heterogéneos.

## Revisit when

Cuando las métricas muestren que la heterogeneidad o rendimiento bloquean el workflow.
