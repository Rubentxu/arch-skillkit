# Estado de implementación V2

Última revisión documental: 2026-09-03.

## Resumen ejecutivo

**V2.1 tiene las fases A–G implementadas y el baseline local reproducible verificado.** El 2026-09-01 pasaron `mise run bootstrap`, `mise run doctor` y `mise run ci`: Python 194/194 en 24.23 s y BATS 69/69 en 159.78 s (159.79 s total). El estado Git posterior coincidió exactamente con el anterior y `git diff --check` quedó limpio. El benchmark canónico UAT2-017 también fue medido para 100 archivos y 10 iteraciones: el Context Compiler realizó 10 lecturas frente a 1.000 del baseline, una reducción del 99,0%, superior al objetivo del 50%. La evidencia es [`2026-09-01-v2.1-baseline.json`](../../artifacts/benchmarks/context-compiler/2026-09-01-v2.1-baseline.json) (SHA-256 `733ac844ae5afb3b0f76318fd92a03356eb60eb0613d7e816e95dedd3f34eb2b`); el RSS pico observado externamente fue aproximadamente 41.060 KiB. La instalación permanece `not_measured` por decisión explícita. Esto no cierra el gate de release: faltan la medición de instalación, evidencia UAT obligatoria consolidada y validar el workflow local con `act`. El preflight `uat-doctor`, bajo el perfil conservador, se detuvo antes de ejecutar escenarios por no disponer del entorno cacheado de `archskillkit` ni de Semgrep; es un bloqueo de preparación, no un fallo funcional ni una UAT fallida. La fase H (SCIP) sigue siendo un spike condicional.

## Tracker de iniciativas

| Iniciativa | Estado | Evidencia y trabajo abierto |
|---|---|---|
| V1 | Baseline entregado | Pipeline shell en `scripts/`, Skill y cobertura BATS en `tests/`. |
| V2.1 ActiveGraph/Python | Implementado; benchmark/KPI parcial completado | Fases A–G en `python/src/archskillkit/` y `python/tests/`. UAT2-017 midió el KPI con resultado PASS para su carga canónica; el [plan UAT trazable](uat/v2.1-plan.yaml) permanece sin evidencia obligatoria consolidada, y falta la medición de instalación. |
| V2.2 Projection Applications | Implementada (F10 de V2.3); validación externa parcial | Cinco writers productivos: LikeC4, Arrows, GraphML, JSON Canvas y draw.io en `projections/adapters/`, con protección real de ediciones manuales, lifecycle y routing. Falta evidencia UAT en consumidores externos (Cytoscape/Gephi/yEd, Obsidian, draw.io) y revisión visual humana del layout draw.io. |
| V2.3 Semantic Integrity & Hardening | COMPLETA (F1–F10) | Ver bloque siguiente; roadmap en [`46-roadmap-v2.3.md`](46-roadmap-v2.3.md). |
| V2.4 Architecture Intelligence & Agent Governance | M0–M4 Implemented; M1 7/8; M5 7/7 | Especificación incorporada en [`49-v2.4-summary.md`](49-v2.4-summary.md) (docs 49–69, ADRs 0032–0045). **M0 Product Kernel completo** (`b4b6bbd`…`37f49e6`): snapshot versionado, RunLedger, RuntimeRegistry, ports, GetStatus/Explain, handlers CLI, coverage baseline. **M1 7/8** (`c892e9b`…`1e42b43`): viewer layer, `schema`/`view`/`ask`, capability matrix, spike Excalidraw DEFER, proofs P-01/P-02 automatizadas con evidencia de imagen; falta P-03 GraphML manual. **M2 Change Intelligence completo** (`ff4d0fa`…`f0d90bd`): ContextQuery tipado, KPIs de contexto, AnalyzeImpact file/symbol/element, KnowledgeGap persistido en world, `ask` NL equivalente al typed, AgentSession con stale detection, Prompt Compiler, bootstrap de agente, UAT source-read policy. **M3 Governance completo** (`4b29854`…`2eb55e6`): History + ArchitectureDelta con golden test, Fitness Profile + waivers + `archskillkit gate` con verdicto determinista y waivers con expiración explícita, multi-formato (json/markdown/sarif), PR delta CLI sobre snapshot states con markdown PR-comment-friendly. **Slice 12 signed snapshot spike** documentada en [`65-signed-snapshot-spike.md`](65-signed-snapshot-spike.md) (Ed25519 sign/verify; CI integration + rotación + revocación quedan como follow-up). **M4 Agent Distribution 7/7** (`10dd000`, `361774f`, `3b35e3e`, `fd583d2`, `087114a`, `45103d2`, `e8fbbd9`): MCP read-only server over stdio (5 read tools), admin-disabled-by-default gate + 9 admin tools (`arch_propose_list/create/diff/review/promote/reject` + `arch_prompt_registry` + `arch_skill_registry` + `arch_simulate`) delegating to `proposals.py` / `simulate.py` CLI logic; candidate→review→promote workflow with base-world integrity (only promote touches base). **M4 Slice 16** (`087114a`) records the prompt-spec hash + per-skill content_hash into every candidate so reviewers can answer "what produced this?". **M4 Slice 18** (`45103d2`) implements `simulate` (counterfactual on a throwaway fork, docs/v2/57 §7): three verbs (`relation add`, `move`, `delete`), `SimulationResult` envelope with `base_snapshot_id`, `base_snapshot_after_id` (byte-identical by internal assertion), `policy_result`, `blast_radius`, `unknowns_opened` and a `recommendation` verb (`allowed|risky|blocked|unknown`). The throwaway fork is dropped after evaluation so the run ledger never accumulates it. `arch_simulate` is exposed as a 9th MCP admin tool. Stable error codes: `ELEMENT_NOT_FOUND`, `INVALID_CATEGORY`, `INVALID_VERB`, `BASE_WORLD_MUTATED`. `world.drop_run(run_id)` is the new primitive that backs the cleanup. CI verde (python 549, bats 75). **M4 Slice 19** (`e8fbbd9`) closes the deterministic-replay gate (docs/v2/56 §10, docs/v2/58 gate "replay fixture without API key") with two halves: `archskillkit replay-fixture <dir>` re-executes the captured scanner-payload pipeline against a sandbox repo and compares the resulting snapshot against `golden.json` (drift on pack/schema/scanner surfaces as `FIXTURE_DRIFT`, exit 1); `archskillkit replay-candidate <name> --fixture <json>` records / verifies a candidate provenance + structural diff + gate verdict against a recorded fixture (drift on any of the three surfaces under `drift.{provenance,structural_diff,verdict}`, exit 1). Both ship a stable envelope schema, deterministic verification, and an MCP read-only tool (`arch_replay_fixture`; candidate replay stays CLI-only since it needs the world). Determinism caveat: the snapshot `digest()` is sensitive to `ProjectData.created_at`, so the pipeline replay uses a `_stable_digest()` over code/policy/knowledge/event_id/code_index stats only. **M4 closed (7/7)**. **M5 Slice 20** Control Plane kernel (`archskillkit control-plane`): servidor HTTP local-only — bind 127.0.0.1 por construcción sin escape hatch, bearer token por proceso impreso una sola vez en stdout como envelope JSON de una línea (nunca persistido), registro/borrado en RuntimeRegistry en shutdown graceful (SIGINT/SIGTERM), y API read-only `/health` + `/status` + `/history` + `/viewers` con los mismos envelopes schema-bound que sus comandos CLI equivalentes; http.server stdlib, cero dependencias nuevas. Pendiente: M5 paneles evidence/coverage, viewer hub, draw.io round-trip, governance opt-in (frontend stack, signed snapshots, Excalidraw re-eval). |

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

Estos nombres identifican iniciativas de producto y **no son versiones SemVer del paquete**. El paquete Python declara `0.3.3` en [`python/pyproject.toml`](../../python/pyproject.toml); el último tag Git es `v0.3.3` (la fuente de versión canónica es pyproject — ver [V2.3, §6](45-v2.3-semantic-integrity-hardening.md#6-fuente-única-de-versión); `scripts/release/sync-versions.py --check` se ejecuta en el gate).

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
| Real OSS validation | Partial: Next.js PASS (1/3) | Pipeline end-to-end sobre `vercel/next.js` @ `ec847d82` (300MB, 3.3k ficheros): 21.315 símbolos ast-grep, 65 endpoints reales detectados por reglas semgrep Next.js nuevas (`next.pages_api_handler`, `next.app_route_handler`), 55 observaciones→claims→87 elementos+55 relaciones, LikeC4 `✓ Valid`, PNG render vía Playwright chromium, invariant UAT2-001 PASS, teardown limpio. Runner: `scripts/oss/run-oss.sh` con caps (4 threads, nice 19, teardown). Bugs reales encontrados y corregidos: `--format all` KeyError en CLI; semgrep OSS ≥1.x no emite `metavars` → fallback de extracción de target por source-slice en `ingest_semgrep` (+5 tests). Pendiente: Axum (Rust) y Django (Python, requiere reglas semgrep nuevas). Plan: `docs/v2/uat/v2.1-real-oss-validation-plan.md`. |
| V2.4 Architecture Intelligence & Agent Governance | Proposed: [`49-v2.4-summary.md`](49-v2.4-summary.md) | Evolución V2.4: conocimiento arquitectónico temporal, verificable, graph-native y agent-native (docs 49–69, ADRs 0032–0045). Sustituye la propuesta V2.2 Product Evolution ([48](48-v2.2-product-evolution.md), SUPERSEDED): corrige sus supuestos (CLI como centro, fitness monodimensional, PID registry en world state). Roadmap en [`58-v2.4-roadmap.md`](58-v2.4-roadmap.md); milestones en [`59-v2.4-milestones.md`](59-v2.4-milestones.md). |

## Camino siguiente

1. **Gate V2.1 cerrado:** el [plan UAT](uat/v2.1-plan.yaml) está completo (16/16 PASS). El `v2-orchestrator` envuelve `archskillkit.world` / `promotion` / `proposals` / `codeindex` / `context`; el `benchmark-harness` mide `source_file_reads` y `peak_bytes` del Context Compiler; el `check-coverage.py` valida hashes de evidencia contra disco. Próximo paso: cortar v0.4.0 con el gate cerrado como evidencia del release.
2. **Ranking del Context Compiler — completado:** proximidad a ficheros cambiados (`CodeIndex.changed_files()`) y delta de grafo reciente (`recent_delta_names()`) integrados en el ranking por relevancia; primera generación degrada a no-op.
3. **Validación real V2.2 (P7) — implementado:** 5 adapters validados con scripts standalone + tests pytest (GraphML/networkx, JSON Canvas/jsonschema, draw.io/lxml, Arrows/jsonschema, LikeC4/likec4 CLI). El piloto LikeC4 destapó y corrigió 2 bugs del adapter. PNG render sigue como follow-up manual (draw.io/likec4) donde se necesite Chrome.
4. **Decidir SCIP con datos:** adoptar, mantener opcional o rechazar (spike condicional, sin fecha).
5. **Distribución offline estricta — trust root Sigstore implementado:** snapshot de la client trust configuration como asset de release, digest fijado en el manifest (`trust_root`) y verificación hermética (`--trust-config --offline`) probada contra el release v0.3.1; la suites `verify-release` la ejercita en el contenedor sin red a partir del release que la incluya. Pendiente: matriz ARM del verify-release (qemu) si hay demanda.
6. **V2.4 Architecture Intelligence & Agent Governance — M0–M4 Implemented, M5 5/7:** M0 kernel completo; M1 con proofs P-01/P-02 automatizadas y solo P-03 GraphML manual pendiente; M2 completo (ContextQuery, KPIs, impact, gaps, ask, sesiones, prompt compiler, bootstrap, UAT source-read); M3 Governance completo (history, delta, fitness, waivers, gate, multi-formato, PR delta); M4 Agent Distribution 7/7 con MCP server (5 read + 9 admin tools), provenance hash en M4 Slice 16, `simulate` counterfactual en M4 Slice 18 (UAT24-044 — base byte-identical por aserción interna) y replay determinista en M4 Slice 19 (UAT24-045). **M5 Slice 20** cerrado: kernel del Control Plane (`archskillkit control-plane`) — servidor local-only 127.0.0.1 con bearer token por proceso, RuntimeRegistry y API read-only `/health`, `/status`, `/history`, `/viewers`. **M5 Slice 21** cerrado: nuevos endpoints `/evidence` (provenance), `/coverage` (cobertura/unknowns), `/gaps` (knowledge gaps abiertos), `/findings` (hallazgos de governance); shell estática en `/` (zero-dependency, WCAG 2.2 AA, reduced-motion-safe, sin acceso a filesystem arbitrario). **M5 Slice 22** cerrado: Viewer Hub con `/projections` (formatos con `artifact_status`, sin paths) y `/launch` POST (schema estricto `{"format","viewer"}`, artifact resuelto server-side desde `ARTIFACT_PATHS`, rechazado antes de routing — mismo orden que `delivery/cli/view.py`; LikeC4/draw.io/system-default son intercambiables. **M5 Slice 23** cerrado (23a–23d): round-trip draw.io probado con navegador real (canal `merge` preserva metadata; JSON descartado con fixture negativo), classifier puro `drawio_delta.py`, endpoint `POST /drawio-candidate` (fork candidato revisable, nunca promueve) y panel de edición en el shell con iframe sandboxed de exact-origin y CSP `frame-src https://embed.diagrams.net`. **M5 Slice 24** cerrado: governance mutations opt-in — `--admin`/`ARCH_SKILLKIT_ADMIN=1` habilita creación de candidatos, promote y reject en el Control Plane (403 `ADMIN_DISABLED` por defecto, handlers del pipeline como fuente única, flag `admin` en `/health`, shell habilita Promote/Reject sólo en sesiones opt-in). **M5 cerrado 7/7.** Pendiente: cerrar P-03 (M1), sesiones OSS Axum/Django. **M5 Slice 26** cerrado: Arrows embed viewer (arrows-embed adapter, mode EMBEDDED, consume arrows, vendor bundle en <data-root>/vendor/arrows/), bridge shape mapper (arrows_bridge.py: arrows-v1 to bridge graph, SHA stable), endpoints GET /vendor/arrows/<path> (static files, no auth, confinado), GET /arrows-artifact (auth, bridge-shaped graph with base_drift), GET/PUT /favorites (auth, persisted at arch_config_root()/favorites.json, validated against viewer ids). Shell: Open embedded Arrows button + iframe panel + postMessage pump + favorites star toggle. Recipe scripts/vendor/build-arrows-embed.sh. Export/save round-trip follow-up.
  **M5 Slice 27** cerrado: Arrows round-trip candidate (arrows_delta.py pure classifier: identity by caption/(type,fromCaption,toCaption), semantic element/relation added/removed, unsupported NO_CAPTION/DUPLICATE_IDENTITY/UNRESOLVED_RELATION_ENDPOINT, POST /arrows-candidate mirroring drawio-candidate flow, shell Create proposal flow via bridge cypher export, promote/reject handlers wired). Still no auto-accept; promote/reject remain slice-24 gated.
  **M6 Slice 29** cerrado: Sensor Distiller (`sensor_distiller.py`) — detecta inferencias LLM repetidas (origin=INFERRED) vía `world.claims_by_run()` que evita herencia de eventos fork, agrupa por `(sorted_subjects, normalised_statement)`, propone `SensorCandidate` con status="candidate" y fixtures vacías (human review antes de promoción). CLI: `archskillkit distill-sensors --repo PATH [--min-runs N]`. `claims_by_run` en world.py filtra por `id > forked_at_event_id` para excluir eventos heredados del parent en runs de tipo fork. Schema salida: arch-skillkit/sensor-distillation-v1.
  **M6 Slice 30** cerrado: Conformance Miner (`conformance_miner.py`) — escanea `world.architecture_relations()` agrupadas por `(rel_kind, source_kind, target_kind)`, propone `ArchitectureRuleCandidate` para patrones con `support >= min_support`, candidate_id determinista como slug `<relkind>-<sourcekind>-<targetkind>`, pre-fill DRAFT rule con statement que dice explícitamente "DRAFT from observed pattern — requires approval". Relaciones con kind de endpoint desconocido son silenciosamente saltadas. Nunca muta el world. CLI: `archskillkit mine-conformance --repo PATH [--min-support N]`, schema `arch-skillkit/conformance-mining-v1`. Approval path: `POST /rule-candidate-record` (admin-gated, schema estricto, 403 sin admin) convierte candidate en `architecture_rule` via `world.record_architecture_rule()` con nombre `<candidate_id>-rule`, idempotente por nombre, 409 `RULE_EXISTS` en duplicados. Tests en `test_conformance_miner.py`.

## V2.5 — Architecture Integrity & Intelligence Kernel

V2.5 es una línea de evolución mergeable sobre V2.4. Objetivo: cerrar la distancia entre la arquitectura conceptual y la física, hacer la alineación medible, reproducible y determinista. Docs en `docs/v2/70-*` a `87-*` y ADRs `ADR-0046-*` a `ADR-0056-*`.

**M0 — Verification Baseline: COMPLETE**

Entry: v0.4.0 main reproducible. Deliverables: contracts, verifier, baseline, gate catalog, traceability, smoke plan.

Baseline `docs/v2/verification/architecture-baseline.json`: 17 findings en 4 reglas. Todos resueltos en milestones posteriores.

**M1 — Governance Application API: COMPLETE**

Slice 1: Application command layer extraída. Arquitectura resultante:
- `application/ports/governance_command.py`: GovernanceCommandPort (protocol)
- `application/commands/governance.py`: GovernanceApplicationService (implementación)
- `application/models/governance.py`: DTOs de comandos y resultados (Pydantic)

Gate M1: 7 violations resueltas (ARC-001 + ARC-009), application_api_coverage = 100%.

**M2 — Composition Root: COMPLETE**

`ArchSkillKitApplication` como Composition Root con lifecycle de world + index.
`application_api_coverage = 100%` (15/15 methods reachable from adapters).

**M3 — ActiveGraph Boundary: COMPLETE (slices 1–3)**

Slice 1: ARC-006 → 0 (arrows_delta rename + world.add_object() público).
Slice 2: application_api_coverage = 100%.
Slice 3: world._arch_app reverse reference para que handlers accedan a app.index sin abrir CodeIndex propio.

Gate M3: ARC violations 17 → 4 → 0.

**M4 — ArchitectureDelta: COMPLETE (slices 1–2)**

Slice 1 (`4b9cf57`): `ark changes` command — live ArchitectureDelta entre main y proposal fork.
Slice 2 (`d1d023e`): DELTA-EXPLAIN-002 — VerdictChange con atribución causal.
Gates: DELTA-DET-001 (determinism SHA256 estable), DELTA-EXPLAIN-002 implemented.

**M5 — CodeGraphQueryPort: COMPLETE**

ARC violations 17 → 0 (CodeGraphQueryPort + ArchitectureWorldPort).

Cambios:
- `application/exceptions.py`: re-export AmbiguousSymbolError.
- `application/commands/governance.py`: ArchitectureWorldPort type hints (no concrete world import).
- `application/queries/bootstrap.py`: index=None retorna ContextPack mínimo (ARC-005).
- `application/queries/analyze_impact.py`: AmbiguousSymbolError desde application.exceptions.

**M6 — Context & Agent Efficiency: COMPLETE (slices 1–2)**

Slice 1 (`ff20477`): delta-aware context — `ContextCompiler.compile(delta)` pesa elementos añadidos/cambiados.
Slice 2 (`7d4dc7d`): stale-session rules con fixture completa (3 dimensiones: world_revision, code_generation, policy_revision).

Gates: stale detection = 100% fixture coverage, delta-aware ranking activo.

**M7 — Learning Architecture: COMPLETE (slices 1–2)**

Slice 1 (`66f4ab7`): `promote-sensor` CLI + `sensor_rule` world object + `SensorRuleData` model.
Slice 2 (`0e22fd1`): `reject-sensor` CLI + `distill-sensors --record` + `SensorCandidateData` model + `sensor_candidate` world object.

Flujo completo: `distill-sensors --record` → `reject-sensor | promote-sensor`.
UAT25-070..072 cubiertos. UAT25-073 (ROI) pendiente de campaign run.

**Gate V2.5: 0 ARC violations · 143 tests pass**

Commits V2.5: `f753898` (M3.1) → `4b9cf57` (M4.1) → `d1d023e` (M4.2) → `71c5658` (M5) → `b1c201b` (M3.3) → `ff20477` (M6.1) → `7d4dc7d` (M6.2) → `66f4ab7` (M7.1) → `0e22fd1` (M7.2) → `b1c201b` → `main`.
