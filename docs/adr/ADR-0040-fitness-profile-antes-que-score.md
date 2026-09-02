# ADR-0040 — Fitness Profile multidimensional antes que score compuesto

Status: Proposed

## Contexto

Un score único incentiva Goodhart, oculta N/A y mezcla señales no equivalentes.

## Decisión

La API/gates exponen dimensiones explícitas: drift, evidence coverage, freshness, unknowns, review debt, policy/sensor coverage, projection validity, unexplained change.

Score/grade puede derivarse como presentación secundaria para badge/trend, con fórmula versionada.

## Gate rule

CI debe preferir invariantes explícitas antes que `--min-fitness`.
