# V1 Implementation Specification

## Scope

Implementar una vertical slice que pueda:

1. ejecutarse desde un repo cualquiera;
2. usar instalación global;
3. crear workspace externo;
4. producir evidence bundle;
5. generar LikeC4;
6. generar Arrows;
7. revisar resultados;
8. verificar working tree intacto.

## Inputs

Required:

- current working directory o explicit repo path.

Optional:

- workspace root override;
- agent-specific context;
- overrides externos;
- scan profile.

## Outputs

Persistent:

```text
project.json
knowledge/
likec4/
arrows/
reports/
```

Run-specific:

```text
raw evidence
run manifest
warnings
```

Regenerable cache:

```text
scanner caches
temporary exports
```

## Failure semantics

### Tool unavailable

- mark capability unavailable;
- continue partial si es seguro;
- no inventar findings sustitutorios.

### Scanner error

- preserve raw stderr/log;
- mark run partial/failed;
- do not overwrite last known-good model destructively.

### Invalid LikeC4

- model stage fails;
- previous valid model retained;
- reviewer report includes parser error.

### Repository dirty

El repo puede empezar dirty.

Comparar snapshot inicial/final; no exigir clean inicial.

Fail sólo si ArchSkillKit altera el estado.

## Idempotency

Mismo repo/commit/toolchain debe reutilizar project identity.

Rerun debe ser conservador con:

- overrides;
- declarations;
- manual notes.

## Compatibility

V1 primary platform:

- Linux.

V1 primary stacks:

- Rust;
- Kotlin/Java;
- TypeScript.

## Explicit deferred behavior

No resolver:

- full call graph;
- whole-program type system;
- taint;
- runtime topology;
- historical architecture.

Estas capacidades deben devolver `unsupported/deferred`, no fingir soporte.
