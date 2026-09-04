# ADR-0049 — CodeGraphQueryPort and Provider SPI

Status: Proposed

## Decision

Application consume `CodeGraphQueryPort`. Ingestion/queries/store se separan
progresivamente. ast-grep, Semgrep y futuros índices precisos son providers.

## Rationale

Evitar que CodeIndex sea compilador/parsing framework multilenguaje.

## Verification

`CODE-PORT-001`, provider contract suite, UAT25-050..052.
