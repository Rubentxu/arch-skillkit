# Fork / Diff de arquitectura

## Use cases

- arquitectura alternativa;
- refactoring proposal;
- evaluar prompts/agentes;
- probar policies.

## Workflow

```text
Current run
  │
 fork
  ▼
Proposal run
  │
agent/behaviors
  ▼
architecture candidate
  │
diff
  ▼
review
 ├─ reject
 ├─ keep scenario
 └─ promote
```

## Diff

Debe representar:

- elementos añadidos/eliminados;
- relaciones añadidas/eliminadas;
- confidence modificado;
- evidence cambiado;
- findings nuevos/resueltos.

## Value

Permite experimentar con arquitectura emergente sin destruir el estado aceptado.
