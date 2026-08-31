# Observabilidad y provenance

## Objetivo

Poder responder:

- qué se ejecutó;
- con qué versión;
- contra qué commit;
- qué produjo cada finding;
- qué decidió el agente.

## Run manifest

Cada ejecución debe registrar:

```text
run_id
project_id
commit
start/end
tool versions
skill version
enabled scanners
outputs
warnings
errors
```

## Deterministic outputs

Conservar raw outputs durante una ventana configurable.

## Agent trace

No necesitamos chain-of-thought.

Sí necesitamos decisiones auditables:

```text
claim
evidence references
confidence
assumptions
resulting model change
```

## Metrics V1

- duración total;
- duración por scanner;
- nº ficheros;
- nº findings;
- nº relaciones high/medium/low;
- nº targeted code reads;
- nº relaciones sin evidencia;
- nº warnings reviewer;
- tamaño del evidence bundle.

## Métrica clave

`targeted_code_reads / repository_files`

Debe bajar respecto al baseline agent-only.
