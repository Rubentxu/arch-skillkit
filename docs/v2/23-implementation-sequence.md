# Secuencia de implementación recomendada

Las fases V2.1 A–G ya tienen implementación y tests asociados. El baseline local reproducible pasó el 2026-09-01; la secuencia continúa con performance y UAT antes de añadir capacidad.

## 1. Baseline reproducible — completado localmente

1. `mise run bootstrap`: PASS.
2. `mise run doctor`: PASS.
3. `mise run ci`: PASS; Python 194/194 y BATS 69/69.
4. Estado Git antes/después idéntico y `git diff --check` limpio.

Exit local alcanzado para la receta canónica. Queda ejecutar el workflow local con `just ci-github-local` y decidir si el soporte declarado Python `>=3.11` se mantiene o se alinea con el baseline fijado en `3.12.11`.

## 2. Performance y UAT V2.1

1. UAT2-017 está capturado para ingest, query, Context Compiler y memoria en la carga canónica de 100 archivos × 10 iteraciones; la instalación sigue sin medir.
2. El objetivo de >=50% menos source reads está medido y PASS: 99,0% (10 lecturas del compilador frente a 1.000 del baseline).
3. Ejecutar los UAT obligatorios y consolidar evidencia, además de medir la instalación cuando haya recursos.

Exit: benchmark comparable, medición de instalación y gate UAT trazable cerrado.

El contrato operativo ya está preparado en [`uat/v2.1-plan.yaml`](uat/v2.1-plan.yaml),
con un registro inicial de 16 sesiones `NOT_RUN`, manifiesto inmutable y reporte
consolidados como plantillas. Cada sesión exige su manifiesto homónimo y hashes
SHA-256 de evidencia dentro de su propio directorio; no sustituyen la ejecución
futura ni declaran cobertura. La salida del runner se importa desde
`$UAT_STATE_BASE/runs/<runner-run-id>/`; `payloads/replay.txt` es texto y se
copia/hashea antes de poder referenciarse desde una sesión.

### Harness reproducible y evidencia registrada

El harness ligero está en
[`python/benchmarks/context_compiler.py`](../../python/benchmarks/context_compiler.py).
No usa `pytest` ni un framework de benchmarks: genera un corpus determinista,
mide ingest, query indexada, Context Compiler y memoria pico aislada por
operación, y exige persistir la evidencia JSON.

Cuando haya recursos para medirlo, ejecutar desde la raíz del repositorio:

```sh
PYTHONPATH=python/src python python/benchmarks/context_compiler.py \
  --files 100 --iterations 10 \
  --output artifacts/benchmarks/context-compiler/YYYY-MM-DDTHHMMSSZ.json
```

La ubicación canónica de evidencia es
`artifacts/benchmarks/context-compiler/<run-id>.json`; usar un nombre de run
único y conservar el JSON producido. Contiene ID y timestamp del run,
plataforma, Python, procedencia del paquete, argv de invocación, carga de
trabajo, tiempos y memoria pico por fase. `peak_bytes` corresponde solamente a
la operación indicada: `tracemalloc` se reinicia entre ingest, query, Context
Compiler y baseline.

La instalación está desactivada por defecto y **no se ejecuta** con la
invocación anterior. Cuando haya recursos y una persona decida medirla, debe
optar explícitamente por `--measure-installation` y proporcionar una matriz
JSON de argv, nunca un string de shell. Por ejemplo:

```sh
PYTHONPATH=python/src python python/benchmarks/context_compiler.py \
  --output artifacts/benchmarks/context-compiler/YYYY-MM-DDTHHMMSSZ.json \
  --measure-installation \
  --installation-command-json '["python", "-m", "pip", "install", "."]'
```

Sin ese opt-in, la evidencia registra instalación como `not_measured` con la
razón `not_requested`. Con el opt-in, registra argv, duración, estado y el
resultado del proceso.

El KPI compara, para las mismas solicitudes, los `source_file_reads` del
Context Compiler contra un baseline que lee todos los archivos ya indexados en
cada solicitud. El objetivo es una reducción de al menos 50%. El KPI se marca
inválido y no cumplido si no hay resultados de query, snippets de fuente y
lecturas reales positivas del compilador; por tanto nunca puede declarar una
reducción desde cero reads. `context_reads` se conserva como alias compatible
de `compiler_calls`; los reads reales y los bytes se reportan por separado.
La evidencia canónica ya registrada es
[`2026-09-01-v2.1-baseline.json`](../../artifacts/benchmarks/context-compiler/2026-09-01-v2.1-baseline.json)
(SHA-256 `733ac844ae5afb3b0f76318fd92a03356eb60eb0613d7e816e95dedd3f34eb2b`).
Corresponde a 100 archivos y 10 iteraciones: el baseline realizó 1.000 lecturas
de fuente y el compilador 10, por lo que el KPI quedó en 99,0% y PASS. El RSS
pico observado externamente fue aproximadamente 41.060 KiB. La instalación se
registra como `not_measured` porque no se solicitó el opt-in. Este resultado
completa benchmark/KPI sólo para esa carga canónica; no sustituye la medición de
instalación ni la evidencia de los UAT obligatorios.

El `uat-doctor` se ejecutó con el perfil conservador y se bloqueó antes de
ejecutar escenarios: faltaban el entorno cacheado de `archskillkit` y Semgrep.
Es un bloqueo de preflight que se resolverá con los recursos necesarios, no una
UAT funcional fallida.

## 3. SCIP por evidencia

Ejecutar el spike sólo si el baseline descubre un vacío relevante. Comparar cobertura, coste de indexación, tamaño, latencia e instalación; decidir `adopt`, `optional` o `reject`.

## 4. Cierre V2.1

Revisar documentación, rollback y contratos; reconciliar el paquete `0.2.0.dev0` con la versión de release y crear tag sólo con los gates cerrados.

## 5. Continuar V2.2 por slices

```text
writer → fixtures → tests → UAT → documentación
```

Después completar redacción y thresholds/routing productivo. Foundation, LikeC4 y Arrows se reutilizan; draw.io, JSON Canvas y GraphML no se marcan como entregados hasta que exista su writer productivo. Las especificaciones 24–43 del bundle de integración ya están absorbidas en `docs/v2/`; el bundle no se usa como tracker.

Tracker vigente: [`STATUS.md`](STATUS.md).
