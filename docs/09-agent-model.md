# Modelo de agentes

## Principio

Los agentes son **roles lógicos**, no procesos ni servicios.

V1 no necesita framework multiagente.

## Roles

### Scanner

Responsabilidad:

- identificar proyecto;
- elegir scanners aplicables;
- ejecutarlos;
- preservar outputs;
- registrar provenance;
- no interpretar arquitectura salvo metadata trivial.

### Discovery

Responsabilidad:

- leer evidence bundle;
- identificar sistemas, módulos, integraciones y posibles fronteras;
- listar incertidumbres;
- solicitar lecturas de código sólo cuando aporten valor.

### Modeler

Responsabilidad:

- mantener LikeC4;
- elegir nivel C4 adecuado;
- adjuntar evidence metadata;
- crear views útiles;
- evitar sobre-modelado.

### Reviewer

Responsabilidad:

- cuestionar relaciones;
- verificar evidencia;
- detectar contradicciones;
- comprobar que no se ha ensuciado el repo;
- comprobar validez del modelo.

## Policy de lectura de código

El LLM debe preferir:

```text
evidence → targeted read → inference
```

frente a:

```text
browse repository recursively
```

## Handoff

Los roles intercambian ficheros, no memoria oculta.

Ejemplos:

- evidence bundle;
- `assumptions.yaml`;
- `review-findings.md`;
- LikeC4 source.

## Agent portability

La semántica del workflow debe vivir en la Skill y referencias Markdown, no en features exclusivas de un proveedor.
