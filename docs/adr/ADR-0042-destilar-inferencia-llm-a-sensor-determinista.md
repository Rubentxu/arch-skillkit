# ADR-0042 — Destilar inferencia LLM repetible a sensor determinista

Status: Proposed

## Contexto

Pagar razonamiento probabilístico repetidamente para un patrón ya comprendido es ineficiente y reduce reproducibilidad.

## Decisión

Introducir workflow:

```text
repeated supported inference
 -> SensorCandidate
 -> positive/negative fixtures
 -> ast-grep/Semgrep candidate
 -> tests/UAT
 -> SensorPackRevision accepted
```

Nunca auto-generar/activar reglas sin validation gate.

## KPI

Medir precisión/recall y LLM calls/tokens evitados tras adopción.
