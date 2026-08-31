# Resumen V2

## Decisión

Pivotar desde una futura capa Go-centric hacia Python + ActiveGraph.

ActiveGraph cubre capacidades que sí aportan directamente al objetivo:

- event sourcing;
- replay;
- fork/diff;
- policies;
- behaviors;
- relation behaviors;
- tools;
- LLM events;
- packs;
- graph projection;
- provenance.

## Frontera

ActiveGraph no sustituye al Code Graph determinista.

### Evidence Graph / Code Index

Pregunta: ¿qué existe en el código?

- regenerable;
- determinista;
- alto volumen;
- SQLite.

### Architecture World

Pregunta: ¿qué sabemos, inferimos, decidimos y proponemos?

- event-sourced;
- auditable;
- forkable;
- semántico.

## Fuente de verdad

```text
ActiveGraph Event Log = source of truth
Architecture Graph = current projection
LikeC4 = architecture projection
Arrows = exploration projection
```

## Política tecnológica

La capa propia permanecerá en Python + ActiveGraph.

Si aparecen cuellos de botella:

1. optimizar consultas SQLite;
2. mejorar índices y batching;
3. introducir incrementalidad y cachés;
4. usar multiprocessing/subprocess cuando proceda;
5. evaluar backends existentes;
6. reutilizar herramientas nativas externas.

No se contempla reescribir ni crear componentes propios en Go.
