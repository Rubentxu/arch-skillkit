# Política tecnológica — Python + ActiveGraph

## Decisión

La capa propia de ArchSkillKit se implementará en **Python + ActiveGraph**.

No existe un roadmap de migración, aceleración o reimplementación propia en Go.

## Qué pertenece a Python

- dominio;
- ontología;
- integración ActiveGraph;
- ingestión y normalización;
- Code Index orchestration;
- Context Compiler;
- policies;
- behaviors;
- proyecciones;
- CLI/facade si aparece;
- lifecycle del workspace.

## Qué permanece externo

El trabajo especializado se delega a herramientas existentes:

- ast-grep;
- Semgrep;
- SCIP;
- Git;
- build tools;
- LikeC4;
- Arrows;
- CodeQL opcional en el futuro;
- otros sensores maduros.

## Política de rendimiento

Ante un cuello de botella:

1. medir antes de optimizar;
2. optimizar schema/queries/índices SQLite;
3. reducir volumen y granularidad;
4. introducir procesamiento incremental;
5. batch de escrituras;
6. cachés;
7. multiprocessing cuando tenga sentido;
8. utilizar extensiones/backends existentes;
9. sustituir una dependencia concreta si otra existente funciona mejor.

## Regla

No introducir un segundo lenguaje propio sólo por rendimiento potencial.

El proyecto prioriza:

- cohesión;
- mantenibilidad;
- velocidad de evolución;
- simplicidad de distribución;
- integración natural con ActiveGraph y ecosistema agentic Python.

## Native tooling

Que los scanners estén implementados en Rust, Go, C++ u otros lenguajes es irrelevante para esta decisión.

La restricción afecta al **código propio del producto**, no a las herramientas externas que reutilizamos.
