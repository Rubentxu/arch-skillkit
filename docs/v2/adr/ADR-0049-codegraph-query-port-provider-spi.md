# ADR-0049 — CodeGraphQueryPort and Provider SPI

Status: Accepted with known gap

## Verification evidence

`rg "CodeGraphQueryPort" python/src/` = 0 matches — `CodeGraphQueryPort` remains absent from the python/src tree.
By contrast, `ArchitectureWorldPort` is implemented at `python/src/archskillkit/ports.py:17`.
M5 (Provider Model) gate is blocked on this gap; `CodeGraphQueryPort` is absent from the codebase.

## Decision

Application consume `CodeGraphQueryPort`. Ingestion/queries/store se separan
progresivamente. ast-grep, Semgrep y futuros índices precisos son providers.

## Rationale

Evitar que CodeIndex sea compilador/parsing framework multilenguaje.

## Verification

`CODE-PORT-001`, provider contract suite, UAT25-050..052.
