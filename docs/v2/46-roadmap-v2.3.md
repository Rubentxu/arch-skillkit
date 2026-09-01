# Roadmap V2.3 — Semantic Integrity & Architectural Hardening

Plan de ejecución de la iniciativa definida en
[45-v2.3-semantic-integrity-hardening.md](45-v2.3-semantic-integrity-hardening.md),
derivada de la [auditoría de septiembre 2026](44-architecture-review-2026-09.md).

Principio rector: **el siguiente evolutivo no añade features**. Primero
integridad semántica y límites reales; después, sobre base sana, el resto
de V2.2.

## Reglas de juego

- Cada fase termina con: tests de la fase en verde, suite completa en verde
  (`mise run ci`), y documentación actualizada.
- Ninguna fase rompe el contrato público del CLI salvo las fases que lo
  amplían (F6, F7).
- Las decisiones abiertas (D-1, D-2) no bloquean el inicio.

## Decisiones abiertas

| id | Decisión | Opciones | Estado |
|---|---|---|---|
| D-1 | ¿CI automática de PR/push en `.github/workflows/`? | (a) mantener política actual (Actions solo release gate, CI local como fuente de verdad); (b) reactivar PR CI con la misma receta `mise run ci` | **RESUELTA (a)** — la política CI del repo se mantiene; la receta verde única es `mise run ci`, ejecutada localmente y por el gate de release |
| D-2 | Fuente única de versión | (a) pyproject como fuente + sync script; (b) setuptools-scm desde el tag | **RESUELTA (a)** — pyproject es la fuente; `scripts/release/sync-versions.py --check` en el gate |

## Fases

### F1 — Correcciones P0 de dominio (semántica)

1. **Generaciones de scan** (`ScanGeneration`, staging + promoción atómica;
   invariante PR-2).
2. **`path()` dirigido**: `directed_adjacency()` /
   `reverse_adjacency()` / `undirected_neighborhood()`; tests PR-1.
3. **Cardinalidad de predicates**: `SensorContract` mínimo (metadata
   `cardinality`); contradicción solo en `ONE`; tests PR-5; corregir el test
   que codificaba la semántica incorrecta.
4. **`promote()`**: resolver extremos por nombre semántico antes de buscar
   la víctima; test de propiedad PR-3 (fixpoint del diff).
5. **Protección real de ediciones manuales**: `generated_sha256` +
   `source_revision` + `adapter_version` en el sidecar; comparación antes de
   regenerar; tests PR-4 (UAT-P12 pasa de nominal a real).

Aceptación: los cinco invariantes PR-1…PR-5 en verde como parte de la suite.

### F2 — CI y release con una sola receta

1. El gate de release ya usa `mise run bootstrap` + `mise run test:bats`
   (hecho en v0.2.0); consolidar: el release ejecuta literalmente
   `mise run ci` (que a su vez ejecuta test:python + test:bats).
2. Cerrar D-1. Si (b): restaurar `.github/workflows/ci.yml` con la misma
   receta; si (a): documentar en CONTRIBUTING que la CI local ES el gate y
   cómo ejecutarla (`just ci-github-local` / `mise run ci`).
3. Gates de calidad base: ruff + mypy progresivo + pytest-cov (informe, sin
   umbral bloqueante aún).

Aceptación: una sola definición de «verde», ejecutable localmente y en el
release; cero conocimiento de entorno duplicado en workflows.

### F3 — `ProjectContext` y desconexión CodeIndex→World

1. Introducir `ProjectContext.for_repo()`.
2. `CodeIndex` deja de importar `world` (fitness function en verde).
3. CLI y baterías de tests usan el contexto; comportamiento observable
   idéntico (ids de proyecto estables).

### F4 — Encapsulación real de ActiveGraph

1. `ArchitectureWorldPort` + `ActiveGraphWorldAdapter` con las operaciones
   usadas hoy por promotion/proposals.
2. Retirar `.graph` de la superficie usada por servicios; `_run_exists()` y
   esquema interno quedan en el adapter.
3. Fitness: `promotion`/`proposals` sin `world.graph` (dogfooding-ready).

### F5 — `SensorContract` completo + `EvidenceId`

1. Metadata completa (`fact`, `subject_metavar`, `target_metavar`,
   `target_kind`, `cardinality`, `confidence`) + validador de contratos.
2. Eliminar `_EDGE_RULES` y `_literal_from_metavars()`; intérprete genérico.
3. `match_start/match_end` reales; owner por *smallest containing range*
   (adiós `_MAX_CONTAINER_DISTANCE`).
4. `EvidenceId` content-addressed en promoción, stale y dedup.
5. Primer sensor pack de muestra (spring) publicado como demo del modelo.

### F6 — Split moderado de World/CLI

1. Facade + `ClaimRepository` + `ArchitectureRepository` +
   `ArchitecturePolicyService` + `ProposalService`.
2. Use cases explícitos (Discover, Context, Project, Review, Drift,
   Proposal) — ya existen como funciones; formalizar el borde.
3. CLI sin métodos privados de dominio (fitness function).

### F7 — Drift real por generaciones

1. `diff(generación N-1, N)` → semantic deltas (edges añadidos/eliminados,
   endpoints cambiados, datastore/topic/client nuevos).
2. Delta → architecture mapping → policy evaluation → findings de drift
   con trazabilidad a la generación y al commit.
3. UAT: commit que introduce `Domain → PostgresAdapter` produce un finding
   de drift sin reescanear el mundo completo.

### F8 — Property-based tests + gates estrictos

1. Catálogo PR-1…PR-5 con hypothesis + generadores de grafos/índices.
2. Umbrales de coverage bloqueantes (solo tras F1-F6).
3. Dogfooding como gate: ArchSkillKit analizando ArchSkillKit con el pack
   de reglas self (fitness functions del diseño §5).

### F9 — Modelado C4: estructura vs interfaz

1. Separar estructura (system/container/component) de interfaz
   (endpoint/topic/datastore-interface/port) en el modelo y en el adapter
   LikeC4.
2. `POST /orders` deja de ser `external_system`; pasa a interfaz expuesta
   de su container.
3. Regenerar golden templates; revisar visualmente (human review pendiente
   como siempre).

### F10 — V2.2 sobre base sana: GraphML → JSON Canvas → draw.io

1. **GraphML**: adapter + routing + UAT con Cytoscape/Gephi/yEd.
2. **JSON Canvas**: adapter + UAT con Obsidian/visores canvas.
3. **draw.io**: adapter + UAT de edición estable.

Herencia automática: protección real de ediciones, lifecycle, metadata y
routing ya corregidos en F1-F6.

## Dependencias

```text
F1 ──► F2 ──► F3 ──► F4 ──► F5 ──► F6 ──► F8 ──► F10
                │                │
                └────► F7 ◄──────┘ (F7 requiere F1.1 y F5)
F9 independiente de F7/F8; requiere F1 (base semántica sana)
```

## Fuera de alcance V2.3

- SCIP (sigue como spike condicional).
- Embeddings/RAG en el Context Compiler (primero ranking determinista
  enriquecido: graph distance, symbol match, relevancia de arquitectura,
  confidence, evidence count, proximidad a ficheros cambiados, delta de
  grafo reciente).
- Servidor MCP propio, backend, multi-agente (no-objetivos históricos).
