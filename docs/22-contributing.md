# Guía de contribución

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
- ejecutar la suite: `bats tests/`;
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
