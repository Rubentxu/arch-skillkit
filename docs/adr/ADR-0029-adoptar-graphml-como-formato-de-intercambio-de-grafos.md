# ADR-0029: Adoptar GraphML como formato de intercambio de grafos

- Status: Accepted
- Date: 2026-08-31

## Context

Cytoscape, Gephi y yEd cubren necesidades distintas pero comparten formatos de grafo.

## Decision

Generar GraphML neutral en vez de integrar individualmente cada aplicación.

## Consequences

### Positive

Un projector habilita múltiples aplicaciones completas.

### Negative / Trade-offs

Algunas features específicas de cada aplicación no estarán disponibles.

## Revisit when

Cuando un caso de uso crítico requiera extensión específica.
