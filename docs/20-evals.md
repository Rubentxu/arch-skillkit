# Estrategia de evals

## Objetivo

Medir si el sistema mejora realmente la comprensión arquitectónica.

## Fixture classes

### Synthetic

Repos pequeños construidos para probar una relación concreta.

Ventajas:

- ground truth;
- rápidos;
- adecuados para reglas.

### Real-world

Repos públicos de tamaño medio.

Ventajas:

- ruido real;
- frameworks;
- edge cases;
- arquitectura imperfecta.

## Dataset mínimo por stack

Rust:

- hexagonal;
- web API;
- messaging o DB.

Kotlin/Java:

- Spring;
- multi-module.

TypeScript:

- Node backend;
- modular application.

## Métricas de scanner

- precision;
- recall cuando haya ground truth;
- false positives;
- execution time.

## Métricas agent

- source reads;
- token usage si se expone;
- model correctness;
- hallucinated relationships;
- unsupported assumptions.

## Métricas de modelado

- LikeC4 valid;
- nº relaciones con evidence;
- nº warnings;
- estabilidad entre reruns.

## Golden outputs

Mantener golden files sólo donde haya determinismo suficiente.

No snapshotear prosa LLM completa.

Preferir assertions semánticas:

```text
contains system X
contains relation A -> B
relation has evidence
does not contain forbidden claim
```
