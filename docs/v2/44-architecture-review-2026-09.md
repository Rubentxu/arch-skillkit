# Auditoría de arquitectura — septiembre 2026

Revisión de hardening sobre `main` (post v0.2.0). Cada hallazgo externo se ha
**verificado contra el código** antes de aceptarse; se indica fichero, línea
y severidad. Estado de la verificación: todos los P0 confirmados salvo
indicación contraria.

Leyenda: **VERIFICADO** (reproducido en el código), **OBSOLETO** (era cierto
cuando se redactó el review externo, ya no lo es), **DECISIÓN** (conflicto
con una política existente que requiere decisión explícita).

## 1. Contexto y método

Se ha revisado estructura, implementación Python (`python/src/archskillkit/`),
ActiveGraph, Code Index, promoción Evidence→Architecture, Context Compiler,
fork/diff, proyecciones, tests, skills, CI/release y documentación.

Método: cada afirmación del review externo se contrastó con el código
fuente. Las que no se pudieron reproducir quedan marcadas. Nada de lo
marcado VERIFICADO procede de la lectura del review: procede del código.

## 2. Valoración global

| Área | Valoración | Comentario |
|---|---|---|
| Diseño conceptual | 8.5/10 | Dos grafos, Evidence First, ActiveGraph, Context Compiler y proyecciones bien planteados |
| Arquitectura hexagonal | 6/10 | Buena intención; dependencia invertida CodeIndex→World y fuga de ActiveGraph |
| SOLID | 6/10 | OCP/DIP bien en projections; SRP y DIP flojos en World/CLI/CodeIndex |
| Connascence | 5.5/10 | Contratos implícitos por strings/nombres; duplicación Bash↔Python |
| Calidad de código | 6.5/10 | Legible y testeado, con bugs semánticos serios (ver P0) |
| Tests | 7.5/10 | Buena cobertura funcional; faltan tests de propiedades/invariantes |
| Reproducibilidad local | 8/10 | mise + uv.lock + toolchain pineada + BATS + pytest |
| CI/release | 8/10 | v0.2.0 publicado y verificado (corrección: ver 4.1); validar entornos completos en el gate |
| V2.1 | ~80 % real | Implementación amplia; UAT y gates sin cerrar |
| V2.2 | ~35-40 % | Foundation + LikeC4/Arrows; faltan GraphML, JSON Canvas, draw.io |

Conclusión: **no rehacer**. La base merece conservarse. La siguiente fase es
hardening arquitectónico y semántico antes de añadir features (iniciativa
[V2.3](45-v2.3-semantic-integrity-hardening.md)).

## 3. Hallazgos P0 (verificados, por severidad de corrección)

### P0-1 — Code Index puede quedar obsoleto tras un nuevo scan

**VERIFICADO.** `files.path` es `UNIQUE`; el ingest borra files del *mismo*
`scan_run_id`, pero un run nuevo tiene otro id. `_ensure_file()` hace
`INSERT OR IGNORE INTO files ...` ([codeindex.py:511](../../python/src/archskillkit/codeindex.py)),
así que el fichero antiguo sobrevive con su `scan_run_id` viejo, y los
símbolos huérfanos (`INSERT OR IGNORE INTO symbols`, línea 518) persisten
indefinidamente. Solo `regenerate()` evita el drift.

Corrección propuesta: **generaciones de scan** explícitas con staging +
promoción atómica (diseño en [45 §2.4](45-v2.3-semantic-integrity-hardening.md#24-scanGeneration-generaciones-de-scan)).
Efecto colateral valioso: diff CodeGraph(N-1) vs CodeGraph(N) para drift
real (ver P1-2).

### P0-2 — `path()` documenta "dirigido" pero usa grafo no dirigido

**VERIFICADO.** El docstring dice *"Shortest directed path"*
([codeindex.py:399](../../python/src/archskillkit/codeindex.py)) pero
`_adjacency()` añade ambas direcciones para cada edge (líneas 588-589:
`source→target` y `target→source`). Por tanto `path(B, A)` resuelve sobre
`A→B`. Contamina Context Compiler, análisis de impacto y explicaciones de
agente.

Corrección: separar `directed_adjacency()`, `reverse_adjacency()` y
`undirected_neighborhood()`; ninguna representación compartida.

### P0-3 — La detección de contradicciones es semánticamente incorrecta

**VERIFICADO.** La regla actual es *mismo `subject` + mismo `predicate` +
`object` distinto ⇒ contradicción*
([promotion.py:170-171](../../python/src/archskillkit/promotion.py)). Con
esa regla son "contradicciones":

- `OrderService uses PostgreSQL` vs `OrderService uses Redis`
- `Orders exposes POST /orders` vs `Orders exposes GET /orders`

Obviamente no lo son. Los predicates necesitan **cardinalidad semántica**
(`ONE`/`MANY`) declarada por el sensor. El test actual codifica la
semántica incorrecta como comportamiento esperado: tests verdes ≠ dominio
correcto.

Corrección: `SensorContract.metadata.cardinality`; contradicción solo sobre
predicates `ONE` (diseño en [45 §2.2](45-v2.3-semantic-integrity-hardening.md#22-sensorcontract-reglas-autodescriptivas)).

### P0-4 — `promote()` no elimina correctamente relaciones removidas

**VERIFICADO.** `structural_diff()` convierte los endpoints de las
relaciones a **nombres semánticos**; `promote()` compara después
`(r["kind"], r["source"], r["target"])` contra las relaciones de main, cuyo
`source`/`target` son **ids de ActiveGraph**
([proposals.py:137-143](../../python/src/archskillkit/proposals.py)). Una
relación eliminada cuyos extremos siguen existiendo nunca se encuentra: el
`victim` es `None` y la eliminación se salta en silencio.

Invariante que faltaría (y que añadiría como test de propiedad):

```text
promote(main, proposal)  ⇒  structural_diff(main, proposal).is_empty()
```

### P0-5 — La protección de edición manual de projections no protege

**VERIFICADO, con matiz.** El guard es
`if old.get("manually_modified") and not force`
([writer.py:92](../../python/src/archskillkit/projections/writer.py)), pero
**nada calcula jamás ese flag**: no existe `artifact_sha256` en el sidecar
ni comparación contenido actual vs contenido generado. El único hash del
fichero (`revision_hash`, línea 41) hashea el *snapshot del mundo* (revisión
fuente), no el artefacto. Resultado actual: `generar → editar a mano →
generar` **sobrescribe** en silencio, salvo que el usuario edite además el
metadata a mano (que es lo único que activa el guard).

Corrección: sidecar con `generated_sha256` + `source_revision` +
`adapter_version`; antes de regenerar,
`sha256(artefacto actual) != generated_sha256 ⇒ MANUALLY_MODIFIED`. Así se
cumple de verdad ADR-0030 / UAT-P12.

## 4. Correcciones al review externo (claims obsoletos o en conflicto)

### 4.1 «Release v0.2.0 fallida» — OBSOLETO

El review analizó un estado anterior. El release **v0.2.0 está publicado y
verificado** (todos los jobs en verde, 9 assets: wheel, runtime manifest,
bundles LikeC4/Semgrep x64+arm64, SHA256SUMS; instalación real probada con
`setup` resolviendo el manifest del release). Hubo dos corridas fallidas
antes de verde; la corrección quedó documentada en el propio historial
(`fix(ci)` ×2) y el gate de release ahora arranca el entorno canónico
(`mise run bootstrap` + `mise run test:bats`).

### 4.2 «Restaurar `.github/workflows/ci.yml` para PR/push» — DECISIÓN

La afirmación «no hay CI automática de PR/push» es cierta, pero es
**deliberada**: la política CI del repositorio reserva GitHub Actions para
el gate de release y establece que la validación local es la fuente de
verdad (receta `mise run ci`). Restaurar CI de PRs contradice esa política.

Lo que SÍ se adopta del review: **una sola receta** para las tres
superficies (local, gate de release y —si se decidiera— PR CI):
`mise run ci`. La decisión de reactivar o no la CI de PRs queda registrada
como punto de decisión en el [roadmap V2.3](46-roadmap-v2.3.md) (D-1), con
el tradeoff de minutos de Actions vs detección temprana en PRs.

### 4.3 «STATUS.md dice 0.2.0.dev0 / v0.1.0» — VERIFICADO y corregido

Era cierto. STATUS.md sigue siendo la única pieza con versiones manuales
escrita a mano; corregido en esta misma revisión y cubierto de forma
estructural por el objetivo «fuente única de versión» de V2.3
([45 §2.6](45-v2.3-semantic-integrity-hardening.md#26-fuente-única-de-versión)).

## 5. Hallazgos P1 (arquitectura y semántica)

### P1-1 — Dependencia invertida CodeIndex → ArchitectureWorld

**VERIFICADO.** `CodeIndex.for_repo()` construye un `ArchitectureWorld`
solo para resolver el path del workspace
([codeindex.py:108-110](../../python/src/archskillkit/codeindex.py)).
Corrección: `ProjectContext` (project_id, repository_root, workspace)
resuelto una vez; ambos dominios dependen de él, no entre sí.

### P1-2 — ActiveGraph no está encapsulado (fuga del ADR-0024)

**VERIFICADO.** `promotion.py` y `proposals.py` usan `world.graph` de forma
extensa (`add_object`, `add_relation`, `patch_object`, `remove_relation`,
`remove_object`, `relations`). Corrección: anti-corruption layer
(`ArchitectureWorldPort` + adapter ActiveGraph); retirar `.graph` de la
superficie usada por servicios de aplicación.

### P1-3 — `ArchitectureWorld` crece hacia God Object

**VERIFICADO por inspección de responsabilidades** (workspace, runtime,
observaciones, evidencia, claims, elementos, relaciones, rules, findings,
drift, stale, forks, replay, snapshots, persistencia). Corrección moderada:
facade + repositorios (`ClaimRepository`, `ArchitectureRepository`) y use
cases; sin frameworks.

### P1-4 — Connascence of Algorithm Bash ↔ Python

**VERIFICADO.** `ids.py` se documenta como *faithful port* de los helpers
bash; hay dos fuentes de verdad para remote normalization, XDG y project
id. Corrección: strangler — los scripts shell consumen
`archskillkit project resolve --json`; Python pasa a autoridad única.

### P1-5 — Connascence por nombres de reglas Semgrep

**VERIFICADO.** `_EDGE_RULES`
([codeindex.py:37](../../python/src/archskillkit/codeindex.py)) cablea
substrings de `check_id` a tipos de edge; `_literal_from_metavars()` toma el
primer literal disponible. Corrección: `SensorContract` — metadata
autodescriptiva en las reglas (`fact`, `target_metavar`, `cardinality`,
`confidence`); Python interpreta un contrato genérico. Habilita sensor packs
independientes (spring, ktor, kafka, sqlx,…) sin tocar el core.

### P1-6 — Evidencia sin identidad de contenido y con línea del contenedor

**VERIFICADO.** La promoción usa `rule/file/source_start_line`, donde la
línea es la del símbolo contenedor, no la del match. Corrección: `EvidenceId
= hash(commit, file, start, end, sensor, rule, fingerprint)` conservando
`match_start/match_end` separados de `container_symbol`. Mejora provenance,
stale, diff, dedup y auditoría.

### P1-7 — `_MAX_CONTAINER_DISTANCE = 2` no escala a código real

**VERIFICADO** ([codeindex.py:44](../../python/src/archskillkit/codeindex.py)).
Un client HTTP en la línea 50 de una función de 80 líneas queda sin owner.
Corrección: guardar `start_line/end_line` de ast-grep y resolver el
*smallest containing symbol range*. Elimina la heurística.

### P1-8 — El drift actual valida políticas del modelo, no drift real

**VERIFICADO.** Lo actual compara `ArchitectureRelation` vs
`ArchitectureRule` (policy check del modelo aceptado). El drift interesante
es *nueva evidencia de código vs arquitectura aceptada*. Con las
generaciones de P0-1, el diff semántico N-1→N alimenta el mapeo y las
políticas: drift por delta, no por reescaneo completo.

### P1-9 — Aplanamiento C4: endpoints convertidos a external_system

**VERIFICADO en adapters.** Corrección conceptual: separar **estructura**
(System/Container/Component) de **interfaz** (Endpoint/Topic/Datastore
interface/Port). `POST /orders` es una interfaz expuesta de `OrdersAPI`, no
un sistema externo.

## 6. Hallazgos P2 (mejora continua)

- **Fuente única de versión**: pyproject/version.json/tag/STATUS — Connascence
  of Value. Elegir una fuente (pyproject o setuptools-scm) y generar el resto.
- **Quality gate Python**: añadir ruff, mypy, pytest-cov, hypothesis (sin
  Sonar). Los cinco tests de propiedad propuestos habrían detectado casi
  todos los P0 de esta auditoría (catálogo en
  [45 §3](45-v2.3-semantic-integrity-hardening.md#3-catalogo-de-tests-de-propiedad)).
- **Dogfooding como fitness functions**: usar ArchSkillKit sobre sí mismo en
  CI como gate (domain no importa ActiveGraph, promotion no toca
  `world.graph`, adapters implementan `ProjectionAdapter`, repo intacto).
- **Context Compiler**: no añadir embeddings/RAG todavía; reforzar ranking
  determinista (graph distance, symbol match, arquitectura-relevancia,
  confidence, evidence count, proximidad a ficheros cambiados, delta de grafo).
- **V2.2 proyectores en orden**: GraphML (desbloquea Cytoscape/Gephi/yEd) →
  JSON Canvas (formato trivial, knowledge maps) → draw.io (más complejo).

## 7. Decisión de fondo

La arquitectura conceptual del proyecto es mejor que su implementación
actual — buena situación. No hay que replantear Python + ActiveGraph, el
modelo de dos grafos, el Context Compiler ni la capa de proyecciones. Hay
que **convertir los límites diseñados en límites reales**, fortalecer la
semántica de facts/evidence y eliminar las duplicaciones de conocimiento.
Eso es [V2.3 — Semantic Integrity & Architectural Hardening](45-v2.3-semantic-integrity-hardening.md).
