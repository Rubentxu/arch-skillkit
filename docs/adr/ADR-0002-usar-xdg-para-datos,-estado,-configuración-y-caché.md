# ADR-0002: Usar XDG para datos, estado, configuración y caché

- Status: Accepted
- Date: 2026-08-31

## Context

Se necesita una convención portable en Linux que evite directorios ad-hoc y permita gestionar ciclo de vida de datos.

## Decision

Adoptar XDG Base Directory Specification como layout principal, con override por variable de entorno.

## Consequences

### Positive

- Convención conocida.
- Separación data/state/cache/config.
- Facilita backup y limpieza.

### Negative / Trade-offs

- Windows requerirá adaptación posterior.
- Hay que documentar bien qué puede borrarse.

## Revisit when

Al ampliar soporte multiplataforma.
