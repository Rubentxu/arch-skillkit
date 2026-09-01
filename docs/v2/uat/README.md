# Gate UAT V2.1

[`v2.1-plan.yaml`](v2.1-plan.yaml) es el contrato trazable del gate obligatorio:
requisito → feature → escenario → sesión → evidencia con hash → veredicto.
Todos sus escenarios parten en `NOT_RUN`; estos archivos no registran una
ejecución, benchmark ni KPI aprobados.

El runner existente (`scripts/uat/uat.sh`) puede aportar sus snapshots Git y
payloads para UAT2-001, y como soporte de proyección para UAT2-009/010. Los
flujos de ActiveGraph V2 deben ser orquestados de forma específica para los
presupuestos y lecturas de contexto (007/008), fork/diff/aprobación
(012–014) y aislamiento entre proyectos (002/003/018).

El registro inicial [`v2.1-sessions.not-run.yaml`](v2.1-sessions.not-run.yaml)
declara las 16 sesiones obligatorias sin resultados. Al ejecutar en el futuro,
una sesión cubre un único escenario y debe tener un manifiesto con el mismo
identificador. Crear la sesión desde [`session.template.yaml`](session.template.yaml),
registrar cada archivo capturado en
[`evidence-manifest.template.yaml`](evidence-manifest.template.yaml) y consolidar
únicamente esas referencias en [`report.template.yaml`](report.template.yaml).
Las sesiones `PASS` con todos los hashes requeridos son las únicas que cuentan
como cobertura. Cada escenario declara dos rutas por artefacto:
`source_path` identifica la salida del runner, orquestador o benchmark; y
`evidence_ref_path` identifica su copia canónica dentro de la sesión. La
cobertura compara siempre `evidence_ref_path`, nunca la ruta temporal o externa
de origen.

## Handoff del runner existente

`scripts/uat/uat.sh` escribe fuera del repositorio bajo
`$UAT_STATE_BASE/runs/<runner-run-id>/` (por defecto,
`${XDG_STATE_HOME:-$HOME/.local/state}/arch-skillkit-uat/runs/`). Sus payloads
incluyen `payloads/replay.txt`, no `replay.json`. Después de una ejecución
futura, importar el árbol sin modificarlo y después registrar sólo copias por
sesión:

```sh
RUNNER_RUN_ID=<id-impreso-por-el-runner>
UAT_STATE_BASE=${UAT_STATE_ROOT:-${XDG_STATE_HOME:-$HOME/.local/state}/arch-skillkit-uat}
SOURCE_RUN="$UAT_STATE_BASE/runs/$RUNNER_RUN_ID"
IMPORT_RUN="artifacts/uat/v2.1/runner-imports/$RUNNER_RUN_ID"
test -f "$SOURCE_RUN/manifest.json" && test -f "$SOURCE_RUN/payloads/replay.txt"
mkdir -p "$IMPORT_RUN"
cp -a "$SOURCE_RUN/." "$IMPORT_RUN/"
```

Para cada escenario se copian los artefactos seleccionados desde `IMPORT_RUN`
a `artifacts/uat/v2.1/sessions/<session-id>/evidence/runner/`, se calcula
`sha256sum` sobre esas copias y se las declara tanto en la sesión como en su
manifiesto. La sesión debe declarar el único `source_runner_run_id` y una
entrada `provenance.allowed_sources` para ese árbol importado. Cada referencia
runner debe repetir ese identificador, `source_path` y `source_sha256`; así la
copia queda ligada al archivo exacto de origen. `session_id` y `manifest_id`
deben coincidir; las rutas canónicas de una referencia deben permanecer dentro
de esa sesión.

UAT2-017 es distinto: su registro de benchmark nace bajo
`artifacts/benchmarks/context-compiler/<benchmark-run-id>.json`. Se importa a
la ruta canónica de la sesión y se declara como fuente `benchmark-harness` en
`allowed_sources`, con su run ID, ruta y hash. Su revisión de métricas del
orquestador se declara como una segunda fuente permitida; ninguna de ambas se
presenta como evidencia del runner existente.

UAT2-015 y UAT2-016 quedan documentados como gaps no obligatorios: no cambian
la cobertura ni pueden cerrar el gate V2.1.

## Perfil de recursos reproducible

El runner y los scanners priorizan máquinas con recursos escasos sin reducir
escenarios ni aserciones: ast-grep usa un hilo, Semgrep usa `--jobs 1` y
LikeC4/Node recibe `--max-old-space-size=512`. Cada límite admite únicamente
un entero positivo sin ceros iniciales mediante `ARCHSK_AST_GREP_THREADS`,
`ARCHSK_SEMGREP_JOBS` y `ARCHSK_NODE_MAX_OLD_SPACE_SIZE_MB`, respectivamente.
`just` reenvía estas variables y el `NODE_OPTIONS` heredado al entorno puro de
Devbox. El runner captura los valores efectivos,
incluido `NODE_OPTIONS`, en `evidence/resource-limits.json` y los replica en
`manifest.json.reproducibility.pipeline.resource_limits`; se deben importar
junto con el resto de la evidencia. La construcción de `NODE_OPTIONS` conserva
las opciones no relacionadas con heap, elimina cualquier heap previo (con
guiones o guiones bajos) y escribe exactamente un `--max-old-space-size`.
