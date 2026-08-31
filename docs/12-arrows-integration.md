# Integración Arrows

## Papel

Arrows es la proyección exploratoria detallada.

No es el source of truth de arquitectura.

## Casos de uso

- navegar dependencias;
- ver ports/adapters;
- explorar endpoints;
- mostrar handlers/events/topics;
- visualizar findings;
- representar relaciones demasiado detalladas para C4.

## Vistas sugeridas

```text
overview.arrows
dependencies.arrows
ports-adapters.arrows
messaging.arrows
endpoints.arrows
data-access.arrows
findings.arrows
```

Generar sólo las aplicables.

## Regla

Arrows puede contener más detalle que LikeC4, pero no debe contradecirlo.

Si aparece contradicción:

1. mantener evidencia;
2. generar finding;
3. no corregir silenciosamente;
4. pedir resolución al Reviewer/humano cuando sea necesario.

## Persistencia

Los `.arrows` viven exclusivamente en el workspace externo.

## Futuro

Si Arrows deja de ser suficiente, debe poder sustituirse sin cambiar la capa de scanning.
