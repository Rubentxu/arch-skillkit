# ADR-0008: Evidence First con DETECTED/INFERRED/DECLARED

- Status: Accepted
- Date: 2026-08-31

## Context

Las inferencias arquitectónicas de LLM deben ser auditables y distinguibles de hechos deterministas.

## Decision

Toda conclusión relevante se clasifica por origen y confidence. DECLARED prevalece sobre DETECTED e INFERRED.

## Consequences

### Positive

- Reduce alucinaciones.
- Hace revisable el modelo.
- Permite overrides.

### Negative / Trade-offs

- Añade disciplina y metadata.
- No elimina ambigüedad real.

## Revisit when

Si se introduce un modelo probabilístico/knowledge graph que requiera taxonomía más rica.
