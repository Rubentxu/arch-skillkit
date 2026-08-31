# Arquitectura de Proyecciones

## Contexto

V2.1 ya separa:

- Code Index;
- Architecture World;
- Context Compiler;
- LikeC4/Arrows.

V2.2 introduce una capa explícita de proyección.

## Componentes

### VisualIntent

Describe qué quiere comunicar el usuario/agente.

### Projection Router

Decide qué formato/aplicación es el mejor destino.

### Projection Adapter

Convierte conocimiento interno a un formato externo.

### Projection Artifact

Fichero generado y recreable.

## Diagrama

```text
                   ActiveGraph
               Architecture World
                       │
                       │
               +-------+-------+
               |               |
               v               v
          Code Index       Decisions
               │               │
               +-------+-------+
                       v
                  VisualIntent
                       │
                Projection Router
                       │
   +-------------------+----------------------+
   |          |               |               |
   v          v               v               v
 LikeC4     Arrows         draw.io        JSON Canvas
                                              |
                                              v
                                           GraphML
                                      /        |        \
                                     v         v         v
                                Cytoscape    Gephi      yEd
```

## Dependency rule

El dominio no importa APIs de las aplicaciones visuales.

Sólo conoce:

- VisualIntent;
- ProjectionRequest;
- ProjectionArtifact;
- ProjectionResult.

## Invariant

Eliminar todos los ficheros de proyección no destruye conocimiento.
