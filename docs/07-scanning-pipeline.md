# Pipeline de scanning

## Objetivo

Reducir el volumen de código que el LLM necesita abrir directamente.

## Fase 0 — Repository discovery

Detectar:

- raíz Git;
- remote;
- branch;
- commit;
- lenguajes;
- build systems;
- manifestos;
- subproyectos/monorepo.

Output:

```text
project.json
```

## Fase 1 — Structural outline

ast-grep:

- clases;
- structs;
- traits/interfaces;
- funciones;
- métodos;
- módulos;
- exports;
- posiciones;
- patrones sintácticos seleccionados.

Output raw:

```text
evidence/raw/ast-grep.jsonl
```

## Fase 2 — Architectural pattern scan

Semgrep:

- endpoints;
- HTTP clients;
- persistence;
- messaging;
- handlers;
- adapters;
- framework annotations;
- integrations;
- architectural violations;
- patrones organizativos.

Output raw:

```text
evidence/raw/semgrep.json
```

## Fase 3 — Build metadata

Ejemplos:

```text
cargo metadata
gradle dependencies
maven dependency tree
package manager metadata
```

Output:

```text
evidence/raw/build/
```

## Fase 4 — Agent selective reads

Sólo cuando la evidencia:

- es ambigua;
- entra en conflicto;
- no resuelve una frontera;
- necesita contexto de negocio.

El agente debe justificar por qué abre código adicional.

## Fase 5 — Model synthesis

El Modeler convierte evidencia válida en:

- systems;
- containers;
- components cuando proceda;
- relationships;
- views;
- metadata;
- assumptions.

## Fase 6 — Review

El Reviewer verifica:

- relaciones sin evidencia;
- contradicciones;
- duplicados;
- niveles C4 incorrectos;
- sobre-modelado;
- elementos huérfanos;
- claims de baja confianza.

## Progressive escalation

Sólo después:

```text
SCIP → semantic resolution
CodeQL → dataflow / taint
Runtime → observed topology
```

No forman parte del camino crítico V1.
