# ADR-0050 — ArchitectureDelta Is First-Class

Status: Accepted

## Verification evidence

`ArchitectureDelta` imported at `python/src/archskillkit/context.py:24` and used as first-class delta type across the codebase.

## Decision

Introducir un delta canonical entre snapshots y reutilizarlo para drift,
changes, PR gates, impact y context.

## Rationale

Reduce connascence de algorithm y hace explicable el cambio de verdict.

## Verification

`DELTA-DET-001`, `DELTA-ID-001`, UAT25-040..044.
