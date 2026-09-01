# Guía de contribución

## Baseline reproducible

El repositorio expone una única interfaz operativa para desarrollo local:

```bash
mise trust mise.toml
mise run bootstrap
mise run doctor
mise run ci
```

`bootstrap` instala el toolchain raíz fijado, reutiliza el runtime de scanners
de la Skill y sincroniza `python/.venv` desde `python/uv.lock` con el extra
`dev`. `doctor` separa dependencias requeridas de herramientas opcionales.
`ci` ejecuta las suites Python y BATS. La receta compatible con GitHub Actions
vive intencionalmente fuera de `.github/`, en `ci/github-actions/ci.yml`, por
lo que GitHub no la detecta ni la ejecuta. Para correrla localmente con `act`:

```bash
just ci-github-local
```

Para ejecutar una sola suite:

```bash
mise run test:python
mise run test:bats
```

Las versiones de ast-grep, Semgrep y LikeC4 pertenecen exclusivamente a
`skills/architecture-discovery/runtime/mise.toml`; no deben duplicarse en la
configuración raíz.

## Filosofía

Una contribución debe preferir:

1. regla;
2. Skill/reference;
3. adapter declarativo;
4. script thin-glue;
5. código propio sólo como última opción.

## Probar scripts (BATS + TDD)

Los scripts thin-glue se prueban con BATS:

- suites en `tests/*.bats`, helpers compartidos en `tests/test_helper.bash`;
- ejecutar la suite: `mise run test:bats`;
- los tests cubren el **seam** del CLI de cada script: exit code, stdout y
  efectos bajo las raíces XDG resueltas; el repositorio fuente debe quedar
  intacto (UAT-001) y los tests no acceden a internos de los scripts;
- desarrollo TDD: test nuevo primero (rojo), implementación mínima después
  (verde), un slice vertical por ciclo; sin tests en lote previos a la
  implementación.

## Añadir una regla Semgrep

Debe incluir:

- propósito;
- lenguajes;
- positive fixture;
- negative fixture;
- expected evidence;
- confidence default.

## Añadir un language pack

Requisitos:

- proyecto fixture;
- scanner strategy;
- reglas high-confidence;
- UAT;
- limitaciones.

## Añadir una dependencia

Responder en PR:

- ¿qué resuelve?
- ¿por qué una herramienta existente actual no basta?
- ¿es required u optional?
- ¿cómo se actualiza?
- ¿cómo se elimina?

## ADR requerido

Para:

- nuevo runtime;
- DB;
- backend;
- MCP propio;
- CLI propio;
- nuevo modelo canónico;
- cambiar repository-clean;
- introducir código de dominio significativo.

## Política de complejidad

Una feature puede rechazarse aunque sea útil si adelanta complejidad de una fase futura sin métricas.
