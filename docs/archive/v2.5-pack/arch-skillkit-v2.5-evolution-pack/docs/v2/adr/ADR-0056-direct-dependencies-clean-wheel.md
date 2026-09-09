# ADR-0056 — Direct Dependencies and Clean-Wheel Verification

Status: Proposed

## Context

Un paquete puede funcionar accidentalmente por dependencias transitivas.

## Decision

Toda librería importada directamente por runtime debe declararse directamente en
packaging. El release gate instala wheel en venv limpio y ejecuta smoke.

## Verification

`PKG-WHEEL-001`.
