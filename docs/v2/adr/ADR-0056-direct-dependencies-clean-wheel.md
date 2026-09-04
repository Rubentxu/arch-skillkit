# ADR-0056 — Direct Dependencies and Clean-Wheel Verification

Status: Accepted

## Verification evidence

`just verify-release` installs the wheel in a clean venv and executes smoke tests; `python/pyproject.toml:12-15` declares all direct runtime dependencies explicitly, preventing accidental reliance on transitive deps.

## Context

Un paquete puede funcionar accidentalmente por dependencias transitivas.

## Decision

Toda librería importada directamente por runtime debe declararse directamente en
packaging. El release gate instala wheel en venv limpio y ejecuta smoke.

## Verification

`PKG-WHEEL-001`.
