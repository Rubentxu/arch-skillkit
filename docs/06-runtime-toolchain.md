# Runtime y toolchain

## Decisión

Usar `mise` como gestor central de:

- versiones;
- instalación de CLIs;
- runtime;
- tareas auxiliares.

## Objetivo

Evitar que cada repositorio de usuario tenga que declarar:

- Node;
- Python;
- Semgrep;
- ast-grep;
- LikeC4;
- otras herramientas futuras.

## Toolchain V1

Requerido:

- git;
- mise;
- ast-grep;
- Semgrep;
- LikeC4.

Opcional por lenguaje/proyecto:

- cargo metadata;
- Maven;
- Gradle;
- npm/pnpm;
- OpenAPI tooling.

## Version pinning

El repositorio ArchSkillKit mantiene versiones probadas como conjunto.

El usuario no debería recibir combinaciones arbitrarias de herramientas.

## Tareas esperadas

Conceptualmente:

```text
doctor
scan
discover
model
review
render
clean-cache
```

No es obligatorio exponerlas como CLI de producto en V1.

## Runtime isolation

La configuración de mise pertenece a la instalación global de ArchSkillKit.

Nunca se copia al repositorio fuente.
