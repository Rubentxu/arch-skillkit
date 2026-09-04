# ADR-0054 — Learning Becomes Deterministic Sensors

Status: Accepted

## Verification evidence

`python/src/archskillkit/sensor_distiller.py:130` — `distill()` function converts repeated LLM inferences into `SensorCandidate` objects for human review before promotion; auto-accept is forbidden by invariant.

## Decision

Inferencias LLM repetidas pueden producir SensorCandidate. Sólo evaluation +
review pueden promover una SensorPackRevision.

## Invariant

LLM no auto-acepta sensor.

## Verification

UAT25-070..073.
