# Estado de implementación V2

Última revisión documental: 2026-09-01.

## Resumen ejecutivo

**V2.1 tiene las fases A–G implementadas y el baseline local reproducible verificado.** El 2026-09-01 pasaron `mise run bootstrap`, `mise run doctor` y `mise run ci`: Python 194/194 en 24.23 s y BATS 69/69 en 159.78 s (159.79 s total). El estado Git posterior coincidió exactamente con el anterior y `git diff --check` quedó limpio. El benchmark canónico UAT2-017 también fue medido para 100 archivos y 10 iteraciones: el Context Compiler realizó 10 lecturas frente a 1.000 del baseline, una reducción del 99,0%, superior al objetivo del 50%. La evidencia es [`2026-09-01-v2.1-baseline.json`](../../artifacts/benchmarks/context-compiler/2026-09-01-v2.1-baseline.json) (SHA-256 `733ac844ae5afb3b0f76318fd92a03356eb60eb0613d7e816e95dedd3f34eb2b`); el RSS pico observado externamente fue aproximadamente 41.060 KiB. La instalación permanece `not_measured` por decisión explícita. Esto no cierra el gate de release: faltan la medición de instalación, evidencia UAT obligatoria consolidada y validar el workflow local con `act`. El preflight `uat-doctor`, bajo el perfil conservador, se detuvo antes de ejecutar escenarios por no disponer del entorno cacheado de `archskillkit` ni de Semgrep; es un bloqueo de preparación, no un fallo funcional ni una UAT fallida. La fase H (SCIP) sigue siendo un spike condicional.

## Tracker de iniciativas

| Iniciativa | Estado | Evidencia y trabajo abierto |
|---|---|---|
| V1 | Baseline entregado | Pipeline shell en `scripts/`, Skill y cobertura BATS en `tests/`. |
| V2.1 ActiveGraph/Python | Implementado; benchmark/KPI parcial completado | Fases A–G en `python/src/archskillkit/` y `python/tests/`. UAT2-017 midió el KPI con resultado PASS para su carga canónica; el [plan UAT trazable](uat/v2.1-plan.yaml) permanece sin evidencia obligatoria consolidada, y faltan instalación y validar el workflow local. |
| V2.2 Projection Applications | Parcial | Foundation, router inicial, lifecycle y LikeC4/Arrows presentes. Faltan writers draw.io, JSON Canvas y GraphML, redacción y thresholds/routing productivo. |

Estos nombres identifican iniciativas de producto y **no son versiones SemVer del paquete**. El paquete Python declara `0.2.0.dev0` en [`python/pyproject.toml`](../../python/pyproject.toml); el único tag Git actual es `v0.1.0`.

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
| P2 — JSON Canvas | Pending | Especificación absorbida; no hay writer productivo |
| P3 — GraphML | Pending | Especificación absorbida; no hay writer productivo |
| P4 — draw.io | Pending | Especificación absorbida; no hay writer productivo |
| P5 — Routing | Partial | Reglas por intent y override presentes; faltan thresholds/política productiva |
| P6 — Lifecycle | Partial | Staleness y protección manual presentes; redacción operativa pendiente |
| P7 — Validación real | Pending | Falta evidencia en tres stacks y consumidores externos |
| P8 — Checkpoint | Pending | Depende de P2–P7 y métricas de uso |

## Camino siguiente

1. **Baseline reproducible local — completado:** bootstrap, doctor y suites Python/BATS verdes sin ensuciar el repositorio.
2. **Cerrar el gate V2.1:** medir instalación y ejecutar el [plan UAT](uat/v2.1-plan.yaml), consolidando sus hashes de evidencia. UAT2-017 y el KPI del Context Compiler ya tienen evidencia para la carga canónica, pero no sustituyen los UAT obligatorios.
3. **Validar la entrega:** ejecutar localmente `just ci-github-local` y resolver la política Python `>=3.11` frente al pin `3.12.11`.
4. **Decidir SCIP con datos:** adoptar, mantener opcional o rechazar.
5. **Cerrar V2.1 y preparar release:** reconciliar versión, tag y changelog.
6. **Continuar V2.2 por slices:** un writer por vez, con fixtures, tests y UAT; después redacción y routing productivo.
