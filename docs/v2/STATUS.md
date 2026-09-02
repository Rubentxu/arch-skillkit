# Estado de implementación V2

Última revisión documental: 2026-09-02.

## Resumen ejecutivo

**V2.1 tiene las fases A–G implementadas y el baseline local reproducible verificado.** El 2026-09-01 pasaron `mise run bootstrap`, `mise run doctor` y `mise run ci`: Python 194/194 en 24.23 s y BATS 69/69 en 159.78 s (159.79 s total). El estado Git posterior coincidió exactamente con el anterior y `git diff --check` quedó limpio. El benchmark canónico UAT2-017 también fue medido para 100 archivos y 10 iteraciones: el Context Compiler realizó 10 lecturas frente a 1.000 del baseline, una reducción del 99,0%, superior al objetivo del 50%. La evidencia es [`2026-09-01-v2.1-baseline.json`](../../artifacts/benchmarks/context-compiler/2026-09-01-v2.1-baseline.json) (SHA-256 `733ac844ae5afb3b0f76318fd92a03356eb60eb0613d7e816e95dedd3f34eb2b`); el RSS pico observado externamente fue aproximadamente 41.060 KiB. La instalación permanece `not_measured` por decisión explícita. Esto no cierra el gate de release: faltan la medición de instalación, evidencia UAT obligatoria consolidada y validar el workflow local con `act`. El preflight `uat-doctor`, bajo el perfil conservador, se detuvo antes de ejecutar escenarios por no disponer del entorno cacheado de `archskillkit` ni de Semgrep; es un bloqueo de preparación, no un fallo funcional ni una UAT fallida. La fase H (SCIP) sigue siendo un spike condicional.

## Tracker de iniciativas

| Iniciativa | Estado | Evidencia y trabajo abierto |
|---|---|---|
| V1 | Baseline entregado | Pipeline shell en `scripts/`, Skill y cobertura BATS en `tests/`. |
| V2.1 ActiveGraph/Python | Implementado; benchmark/KPI parcial completado | Fases A–G en `python/src/archskillkit/` y `python/tests/`. UAT2-017 midió el KPI con resultado PASS para su carga canónica; el [plan UAT trazable](uat/v2.1-plan.yaml) permanece sin evidencia obligatoria consolidada, y falta la medición de instalación. |
| V2.2 Projection Applications | Implementada (F10 de V2.3); validación externa parcial | Cinco writers productivos: LikeC4, Arrows, GraphML, JSON Canvas y draw.io en `projections/adapters/`, con protección real de ediciones manuales, lifecycle y routing. Falta evidencia UAT en consumidores externos (Cytoscape/Gephi/yEd, Obsidian, draw.io) y revisión visual humana del layout draw.io. |
| V2.3 Semantic Integrity & Hardening | COMPLETA (F1–F10) | Ver bloque siguiente; roadmap en [`46-roadmap-v2.3.md`](46-roadmap-v2.3.md). |

**Release v0.3.0 publicada y verificada end-to-end** (5 jobs verdes, 9 assets,
instalación + setup + doctor probados en contenedores Podman limpios vía
`just verify-release`, incluido el camino offline; attestation Sigstore
criptográfica del artefacto).

**V2.3 — Semantic Integrity & Architectural Hardening: COMPLETA (F1-F10).**
Los cinco P0 de la [auditoría de septiembre](44-architecture-review-2026-09.md)
corregidos con invariantes de propiedad, límites hexagonales reales
(`ProjectContext`, `ArchitectureWorldPort`, repositorios), `SensorContract`,
`EvidenceId` content-addressed, drift por generaciones, quality gates
(ruff/mypy/cobertura 74 % con umbral 70 %), fitness de auto-arquitectura,
C4 con estructura vs interfaz y los cinco proyectores. Fase 2 de
[distribución](24-distribution-and-installation.md) implementada en local
(`just verify-release`).

Estos nombres identifican iniciativas de producto y **no son versiones SemVer del paquete**. El paquete Python declara `0.3.0` en [`python/pyproject.toml`](../../python/pyproject.toml); el último tag Git es `v0.3.0` (la fuente de versión canónica es pyproject — ver [V2.3, §6](45-v2.3-semantic-integrity-hardening.md#6-fuente-única-de-versión); `scripts/release/sync-versions.py --check` se ejecuta en el gate).

Política de compatibilidad pendiente: [`python/pyproject.toml`](../../python/pyproject.toml) declara Python `>=3.11`, mientras que el baseline reproducible fija Python `3.12.11`. La verificación local sólo demuestra el entorno fijado; no valida toda la compatibilidad declarada.

## V2.1 por fase

| Fase | Estado | Evidencia estática | Gate pendiente |
|---|---|---|---|
| A — ActiveGraph foundation | Implemented; local suite green | [`world.py`](../../python/src/archskillkit/world.py), packs y [`test_world.py`](../../python/tests/test_world.py) | UAT2-004/018 |
| B — Code Index | Implemented; local suite green | [`codeindex.py`](../../python/src/archskillkit/codeindex.py) y [`test_codeindex.py`](../../python/tests/test_codeindex.py) | UAT2-002/003 |
| C — Evidence → Architecture | Implemented; local suite green | [`promotion.py`](../../python/src/archskillkit/promotion.py) y [`test_promotion.py`](../../python/tests/test_promotion.py) | UAT2-005/006 |
| D — Context Compiler | KPI PASS para carga canónica; UAT pendiente | [`context.py`](../../python/src/archskillkit/context.py), [`test_context.py`](../../python/tests/test_context.py) y [benchmark canónico](../../artifacts/benchmarks/context-compiler/2026-09-01-v2.1-baseline.json) | Consolidar UAT2-007/008/017 y medir instalación |
| E — Projections | Implemented; local suite green | [adapters](../../python/src/archskillkit/projections/adapters) y [tests](../../python/tests/test_projections_adapters.py) | UAT2-009/010 |
| F — Reactive Architecture | Implemented; local suite green | [`world.py`](../../python/src/archskillkit/world.py) y [`test_drift.py`](../../python/tests/test_drift.py) | UAT2-011 |
| G — Fork/Diff | Implemented; local suite green | [`proposals.py`](../../python/src/archskillkit/proposals.py), `world.fork` y [tests](../../python/tests/test_fork.py) | UAT2-012/013/014 |
| H — SCIP spike | Pending / conditional | ADR-0019 y `19-spikes.md` | Ejecutar sólo si las métricas muestran un vacío |
| I — Performance checkpoint | Parcial; benchmark/KPI medidos | UAT2-017: 100 archivos × 10 iteraciones, KPI 99,0% PASS y RSS externo ~41.060 KiB | Medir instalación y completar evidencia UAT obligatoria |

`Local suite green` registra la verificación reproducible del 2026-09-01. No equivale a UAT aprobada, KPI cumplido, release cerrado ni CI remota verde.

## V2.2: especificación absorbida y estado

El bundle ignorado `arch-skillkit-v2.2-projection-applications/` es material histórico de integración, **no una fuente canónica**. Sus documentos 24–43 ya están absorbidos en `docs/v2/` (las únicas diferencias detectadas eran de formato en roadmap y spikes). El tracker canónico es este documento junto con [`37-roadmap-v2.2.md`](37-roadmap-v2.2.md).

| Workstream | Estado | Evidencia / pendiente |
|---|---|---|
| P0 — VisualIntent, ProjectionAdapter y metadata | Implemented; local suite green | `projections/{intents,contract,metadata}.py` |
| P1 — LikeC4 y Arrows normalizados | Implemented; local suite green | adapters productivos en `projections/adapters/` |
| P2 — JSON Canvas | Implemented; local suite green (F10 de V2.3) | `projections/adapters/jsoncanvas.py` + tests; UAT con Obsidian/visores canvas pendiente |
| P3 — GraphML | Implemented; local suite green (F10 de V2.3) | `projections/adapters/graphml.py` + tests; UAT con Cytoscape/Gephi/yEd pendiente |
| P4 — draw.io | Implemented; local suite green (F10 de V2.3) | `projections/adapters/drawio.py` + tests; revisión visual humana del layout pendiente (como todo lo visual) |
| P5 — Routing | Implemented para los cinco formatos | Tabla de preferencias determinista por intent + override del usuario (`projections/router.py`, UAT-P11) |
| P6 — Lifecycle | Implemented | Staleness real + protección de ediciones manuales vía `generated_sha256`/`source_revision`/`adapter_version` (PR-4) |
| P7 — Validación real | Implemented; local suite green | `scripts/projections/validate_*.py` para los 5 adapters (networkx para GraphML, jsonschema para JSON Canvas y Arrows, lxml para draw.io mxgraph, likec4 CLI para LikeC4); tests pytest equivalentes. PNG render queda como follow-up manual para draw.io y LikeC4 (necesita Chrome). El piloto LikeC4 destapó 2 bugs del adapter (relations top-level sin FQN + view `context` reservada) ya corregidos en el commit de P7. |
| P8 — Checkpoint | Pending | Depende de P7 y métricas de uso |
| Gate UAT V2.1 | Implemented: 16/16 PASS | Cobertura completa F-01..F-05. UAT2-001 (runner), UAT2-002/003/018 (F-01 store isolation), UAT2-004/005/006 (F-02 event log/replay/provenance/review), UAT2-007/008 (F-03 Context Compiler budgets + read policy), UAT2-017 (F-03 benchmark-harness: source_file_reads + peak bytes), UAT2-009/010/011 (F-04 LikeC4/Arrows regen + deterministic drift), UAT2-012/013/014 (F-05 fork/diff/promote con policy gate). Pipeline: `scripts/uat/{uat.sh,v2-orchestrator.py,check-coverage.py}`. Plan + registry: `docs/v2/uat/`. |

## Camino siguiente

1. **Gate V2.1 cerrado:** el [plan UAT](uat/v2.1-plan.yaml) está completo (16/16 PASS). El `v2-orchestrator` envuelve `archskillkit.world` / `promotion` / `proposals` / `codeindex` / `context`; el `benchmark-harness` mide `source_file_reads` y `peak_bytes` del Context Compiler; el `check-coverage.py` valida hashes de evidencia contra disco. Próximo paso: cortar v0.4.0 con el gate cerrado como evidencia del release.
2. **Ranking del Context Compiler — completado:** proximidad a ficheros cambiados (`CodeIndex.changed_files()`) y delta de grafo reciente (`recent_delta_names()`) integrados en el ranking por relevancia; primera generación degrada a no-op.
3. **Validación real V2.2 (P7) — implementado:** 5 adapters validados con scripts standalone + tests pytest (GraphML/networkx, JSON Canvas/jsonschema, draw.io/lxml, Arrows/jsonschema, LikeC4/likec4 CLI). El piloto LikeC4 destapó y corrigió 2 bugs del adapter. PNG render sigue como follow-up manual (draw.io/likec4) donde se necesite Chrome.
4. **Decidir SCIP con datos:** adoptar, mantener opcional o rechazar (spike condicional, sin fecha).
5. **Distribución offline estricta — trust root Sigstore implementado:** snapshot de la client trust configuration como asset de release, digest fijado en el manifest (`trust_root`) y verificación hermética (`--trust-config --offline`) probada contra el release v0.3.1; la suites `verify-release` la ejercita en el contenedor sin red a partir del release que la incluya. Pendiente: matriz ARM del verify-release (qemu) si hay demanda.
