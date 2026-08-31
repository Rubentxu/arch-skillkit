# Modelo de evidencia

## Objetivo

Separar observación, inferencia y declaración humana.

## Tipos de conocimiento

### DETECTED

Producido por herramienta determinista.

Ejemplos:

- Semgrep encuentra `@PostMapping`;
- ast-grep encuentra un trait;
- Cargo declara una dependencia;
- OpenAPI declara un endpoint.

### INFERRED

Interpretación del agente.

Ejemplos:

- un trait parece actuar como port;
- un grupo de módulos parece un bounded context;
- una relación parece representar integración externa.

### DECLARED

Información explícita del usuario/proyecto.

Ejemplos:

- `billing` es un bounded context;
- Stripe es sistema externo;
- un path debe ignorarse.

## Prioridad

```text
DECLARED > DETECTED > INFERRED
```

No significa que DETECTED sea infalible; significa que una declaración explícita puede corregir interpretación automática.

## Confidence

V1 utiliza categorías sencillas:

```text
high
medium
low
```

No porcentajes artificiales.

### high

- evidencia inequívoca;
- múltiples fuentes consistentes;
- declaración humana.

### medium

- inferencia razonable;
- una única evidencia contextual;
- resolución incompleta.

### low

- hipótesis;
- naming convention;
- relación sugerida pero no demostrada.

## Regla para LikeC4

Por defecto:

- `high`: puede entrar automáticamente;
- `medium`: entra con metadata/nota o revisión;
- `low`: no se promociona sin validación.

## Provenance mínimo

Cada finding relevante debe poder apuntar a:

- tool;
- rule/query;
- file;
- line/range si existe;
- commit;
- timestamp/run;
- versión de herramienta.

## Formato futuro

Si los outputs heterogéneos se vuelven costosos para los agentes, introducir:

```text
facts.jsonl
```

con esquema canónico.

Esto es deferred y requiere ADR específico antes de implementarse.
