# Seguridad y governance

## Policies

Definir:

- qué tools puede llamar un behavior;
- cuánto source puede leer;
- provider LLM permitido;
- qué mutations requieren approval.

## Human approval inicial

Requerido para:

- promover proposal;
- eliminar DECLARED knowledge;
- cambiar boundary rules;
- exportar/publicar contenido sensible.

## Scanner safety

No ejecutar builds arbitrarios por defecto.

## Audit

Persistir:

- causal events;
- tool calls;
- observations;
- evidence;
- claims;
- decisions;
- approvals.

No persistir chain-of-thought.
