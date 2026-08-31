# Project Registry

## Objetivo

Resolver repositorio → workspace sin escribir metadata en el repositorio fuente.

## Datos mínimos

```json
{
  "project_id": "name-hash",
  "root": "/canonical/path",
  "remote": "normalized-remote-or-null",
  "workspace": "/xdg/data/.../projects/name-hash",
  "last_commit": "sha",
  "created_at": "...",
  "updated_at": "..."
}
```

## Matching

Orden recomendado:

1. canonical root path;
2. normalized remote;
3. explicit alias.

## Monorepos

V1 debe tratar el checkout Git como proyecto raíz.

Puede descubrir subprojects internamente.

No crear un workspace independiente por módulo salvo que se configure explícitamente.

## Move/rename

Si cambia el path pero el remote coincide:

- detectar posible movimiento;
- conservar workspace;
- actualizar registry;
- registrar evento.

## Clones múltiples

Dos checkouts con mismo remote pueden:

- compartir identidad lógica;
- mantener state/run separado si se detectan conflictos.

La política exacta se valida mediante UAT antes de fijarla como contrato.
