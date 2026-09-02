# Changelog

All notable changes to ArchSkillKit are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning is
SemVer (docs/05): MAJOR breaks workspace/evidence/Skill contracts, MINOR
adds compatible capabilities, PATCH covers compatible rules, prompts and
fixes.

## [Unreleased]

## [0.3.1] - 2026-09-02

### Added

- **Context Compiler — recency ranking signals (docs/v2/46, camino
  siguiente)**: the deterministic relevance ranking now also boosts
  elements named by the previous→current scan generation delta
  (`CodeIndex.recent_delta_names()`, +40) and elements whose relation
  evidence lives in files changed between generations
  (`CodeIndex.changed_files()`, +30). Both degrade to no-op on the first
  generation; name tiebreak keeps replay-identical ordering.

### Fixed

- **STATUS.md refreshed**: V2.2 workstreams P2–P4 now reflect the shipped
  GraphML/JSON Canvas/draw.io adapters; version references updated to
  0.3.0/v0.3.0; roadmap pointer renewed.

## [0.3.0] - 2026-09-01

### Added

- **Dogfooding + reglas Python (docs/v2/45 §5)**: `just dogfood` ejecuta
  el pipeline completo del producto sobre el propio repositorio con el
  runtime pineado (reglas outline Python nuevas en el pack ast-grep);
  evidencia en `artifacts/dogfood/`.

- **Fase 2 automatizada en local (docs/v2/24)**: `just verify-release`
  ejecuta en dos contenedores Debian limpios el flujo completo de un
  usuario — instalación del wheel del release, `setup`, `doctor ready`,
  análisis de un repo de prueba (repo intacto), detección de corrupción y
  el camino completo offline (`setup --offline` sin red) — con evidencia
  por ejecución en `artifacts/verify/`. Su primera corrida detectó un
  defecto real (CLI sin `--version`), corregido.

- **V2.3-F2 — quality gates and a single green recipe (docs/v2/46)**:
  `ruff` + scoped `mypy` + `pytest-cov` (73 % informed, non-blocking);
  `mise run lint` / `mise run coverage`; `mise run ci` now runs
  lint + python + bats and is the only definition of green — executed
  locally and by the release gate. `scripts/release/sync-versions.py`
  keeps `version.json` synced from `pyproject.toml` (decision D-2a);
  D-1 resolved as (a): GitHub Actions stays release-gate-only.
- **V2.3-F3/F4 — real boundaries (docs/v2/45 §2.1/§4)**: `ProjectContext`
  (ids.py) resolves project identity once — `CodeIndex` no longer imports
  `ArchitectureWorld`; `ArchitectureWorldPort` (ports.py) formalizes the
  domain surface — promotion/proposals use port methods and `.graph` has
  zero callsites outside world.py (ADR-0024 enforced by construction).
- **Cryptographic attestation verification (docs/v2/24)**: required
  attestations are fetched from the GitHub attestation API
  (snappy-compressed bundles decompressed) and cryptographically verified
  with sigstore (`uv tool install archskillkit --extra attestation`);
  failure or absence is a hard failure (`ATTESTATION_INVALID` /
  `ATTESTATION_MISSING`) — never a silent pass. The manifest generator
  marks self-built artifacts `attestation.required: true` with repository
  identity. draw.io completes the projector set (F10): mxGraph XML with
  deterministic grid layout, opt-in via `project --format drawio` or
  `--format all`.
- **V2.3-F7 — real drift from scan-generation deltas (docs/v2/46 F7)**:
  generation rotation keeps the previous generation queryable
  (`code.prev.sqlite`); `CodeIndex.diff_previous_generation()` reports the
  semantic edge delta; `detect_generation_drift` maps new code
  dependencies into persisted `generation_drift` findings — surfacing in
  `archskillkit drift` output.
- **V2.3-F6 — World split into repositories/services (docs/v2/46 F6)**:
  `repositories.py` hosts `ClaimRepository`, `ArchitectureRepository`,
  `ArchitecturePolicyService` and `ProposalService`; the world facade
  delegates; CLI uses only public surface (`has_run`/`view`).
- **V2.3-F7 — real drift from scan-generation deltas (docs/v2/46 F7)**:
  generation rotation keeps the previous generation queryable
  (`code.prev.sqlite`); `CodeIndex.diff_previous_generation()` reports the
  semantic edge delta and `detect_generation_drift` maps new code
  dependencies into persisted `generation_drift` findings (surfaced in
  `archskillkit drift`); `FindingData.kind` gains `generation_drift`.
- **V2.3-F6 — World split into repositories/services (docs/v2/46 F6)**:
  `repositories.py` hosts `ClaimRepository`, `ArchitectureRepository`,
  `ArchitecturePolicyService` and `ProposalService`; the world facade
  delegates and the CLI uses only public surface (`has_run`/`view`).
- **V2.3-F10 (partial) — GraphML and JSON Canvas projectors
  (docs/v2/32/31)**: two new adapters behind the ProjectionAdapter
  contract (deterministic output, architecture metadata as GraphML data
  keys; JSON Canvas 1.0 with grid layout), wired into
  `archskillkit project --format` and the intent routing preferences.
  draw.io remains the last pending projector.
- **V2.3-F9 — C4 structure vs interface (docs/v2/46 F9)**: endpoint,
  topic, datastore and http_client pseudo-targets become `interface`
  elements of the analyzed system — never external systems; LikeC4
  renders them inside the target system with the `#interface` tag.
- **V2.3-F8 — generated properties, coverage gate and self-architecture
  fitness (docs/v2/46 F8)**: hypothesis-generated DAG properties for
  directed-path semantics; coverage gate at 70 % (`mise run coverage`);
  `tests/test_self_architecture.py` enforces the ADR-0024 boundary, the
  port-only rule for promotion/proposals, the ProjectContext rule for
  CodeIndex and the ProjectionAdapter contract.
- **V2.3-F1 — semantic integrity property tests (docs/v2/46)**:
  `tests/test_properties.py` pins the five domain invariants PR-1…PR-5
  (directed paths, scan-generation replacement, promotion diff-fixpoint,
  manual-edit detection, cardinality-gated contradictions). Verified red
  against the previous code and green after the fixes.
- **V2.3-F5 — SensorContract + content-addressed evidence (docs/v2/45
  §2.2/§2.4)**: scanner rules declare their fact via
  `metadata.archskillkit` (fact, target_kind, target_metavar, cardinality,
  confidence) — check_id substring classification is removed (legacy
  bridge kept for pre-contract payloads); semgrep match spans are stored
  (`match_start/match_end`, Code Index schema v2) and container resolution
  prefers the smallest containing symbol range; `EvidenceData.evidence_id`
  content-addresses provenance and is the promotion dedup key; the three
  shipped sensor packs (kotlin/rust/typescript) declare their contracts.

### Changed

- **V2.3-F1 — domain fixes (docs/v2/44 P0-1…P0-5, docs/v2/46 F1)**:
  - `CodeIndex`: scan generations — ingesting a new `scan_run_id`
    atomically retires the previous generation; facts of retired scans no
    longer survive (`INSERT OR IGNORE` staleness bug).
  - `CodeIndex.path()` is now genuinely directed (separate
    `_directed_adjacency()`); `neighborhood()` keeps undirected exploration.
  - `promotion`: contradictions require a single-valued predicate
    (`PREDICATE_CARDINALITY`, SensorContract v0); `many` predicates never
    contradict.
  - `proposals.promote`: removed relations are matched by semantic element
    names, not runtime ids — removals are no longer silently skipped and
    promotion is a diff fixpoint.
  - `projections`: manual-edit protection is content-based — the sidecar
    records `generated_sha256` and regeneration compares the artifact's
    current hash (UAT-P12 is now enforced, not nominal).
- **V2.3-F2 — quality gates and a single green recipe (docs/v2/46)**:
  `ruff` + scoped `mypy` + `pytest-cov` (73 % informed, non-blocking);
  `mise run lint` / `mise run coverage`; `mise run ci` now runs
  lint + python + bats and is the only definition of green — executed
  locally and by the release gate. `scripts/release/sync-versions.py`
  keeps `version.json` synced from `pyproject.toml` (decision D-2a);
  D-1 resolved as (a): GitHub Actions stays release-gate-only.
- **V2.3-F3/F4 — real boundaries (docs/v2/45 §2.1/§4)**: `ProjectContext`
  (ids.py) resolves project identity once — `CodeIndex` no longer imports
  `ArchitectureWorld`; `ArchitectureWorldPort` (ports.py) formalizes the
  domain surface — promotion/proposals use port methods and `.graph` has
  zero callsites outside world.py (ADR-0024 enforced by construction).

## [0.2.0] - 2026-09-01

### Added

- **Distribution and installation, Python-first (docs/v2/24)**: the
  `archskillkit` CLI installs via `uv tool install` / `pipx`; `setup`
  installs the pinned runtime of external tools (ast-grep 0.45.2,
  Semgrep 1.175.0 in an isolated venv, Node 22.14.0 + LikeC4 1.59.2) from
  a hash-pinned release manifest with atomic activation, digest-addressed
  cache, preflight checks and stable error codes; `doctor` provides a
  read-only JSON installation diagnosis (`ready`, `ready-offline`,
  `incomplete`, `corruption`, `host-insufficient`). The release pipeline
  publishes the wheel, runtime bundles and provenance attestations.
- **User documentation**: user manual and cheat sheet in English and
  Spanish (docs/manual/).
- **V2 Phase G (M2-G1…G4) — fork/diff of the architecture
  (`archskillkit.proposals`)**: architectural proposals on independent
  branches of the project's event log (docs/v2/08):
  - M2-G1/G2 `world.fork(name)`: branches the world run into
    `proposal-<name>` with ActiveGraph's native log fork; proposals
    mutate their fork only — main is untouched (UAT2-012, H2-8);
    idempotent by name; the `proposal` object carries status
    open/approved/rejected/promoted (arch-model v0.3.0).
  - M2-G3 `structural_diff`: compares architecture layers by semantic
    names (never runtime ids) across every docs/v2/08 dimension —
    elements and relations added/removed, confidence changed, evidence
    changed on the same triple, findings new/resolved (UAT2-013, H2-9).
  - M2-G4 `promote`: applies an approved proposal's diff to the main
    world; refused without an approved proposal (UAT2-014), refused for
    rejected ones, idempotent on re-promotion, replay verified after.
  - CLI: `fork`, `diff`, `promote --approved-by`, `reject-proposal`.
  - 17 new tests (194 pytest total).
- **V2 Phase F (M2-F1…F3) — reactive architecture (`world.detect_drift`,
  `world.detect_stale_model`)**: deterministic boundary evaluation
  without an LLM (docs/v2/09, ADR-0022):
  - M2-F1 drift: structured `architecture_rule` objects
    (`source_category -[forbidden_relation]-> target_category`) are
    evaluated against the architecture relations; violations become
    persisted `architecture_drift` findings with rule traceability.
  - M2-F2 contradictions: already deterministic since Phase C
    (evaluate_claims) — unchanged.
  - M2-F3 stale model: evidence backing the accepted architecture whose
    (file, line) location disappears from the current Code Index becomes
    a `stale_evidence` finding (new `CodeIndex.symbol_locations`).
  - Shared finding persistence with review audit objects and
    (kind, target) dedup — review() now reuses it.
  - `arch-model` pack v0.2.0 (architecture_rule); `arch-core` v0.3.0
    (architecture_drift finding kind). CLI `drift`.
  - 12 new tests (177 pytest total).
- **V2 Phase E (M2-E1…E3) + V2.2 P1/P6 slice — world projections on the
  common contract (`archskillkit.projections.adapters` + `writer`)**:
  - M2-E1 LikeC4 projector: the Architecture World renders as a LikeC4
    model mirroring the V1 golden template (validates by construction —
    proven with the pinned likec4 in a BATS seam test); deterministic
    and byte-identical on regeneration (UAT2-009).
  - M2-E2 Arrows projector: world → `arch-skillkit/arrows-v1` document
    with endpoint integrity, regeneration-equivalent (UAT2-010).
  - Both adapters implement the Phase P0 `ProjectionAdapter` contract
    and route through the deterministic router (V2.2 P-H3 normalization);
    artifacts land in the existing `likec4/` and `arrows/` workspace
    directories with a metadata sidecar carrying the source revision.
  - Lifecycle slice (V2.2 P6): staleness detection against the world
    content hash and manual-edit protection — modified projections are
    not silently overwritten (UAT-P12) unless `--force`.
  - M2-E3 consistency: adapter metrics must match the projected snapshot;
    mismatches surface as result warnings.
  - CLI `project` (--format likec4|arrows|both, --force); 18 new tests
    (165 pytest total, 66 BATS).
- **V2 Phase D (M2-D1…D4) — Context Compiler (`archskillkit.context`)**:
  budgeted ContextPacks instead of whole-graph dumps (docs/v2/06,
  design/schemas/context-pack.yaml):
  - M2-D1 `ContextPack` schema (goal/intent/summary, architecture view,
    code facts, evidence, snippets, uncertainties, budget) matching the
    design YAML with deterministic summary and intent classification.
  - M2-D2 budgeted queries: subject resolution narrows the world,
    expansion is bounded to one relation hop, and node/edge budgets are
    enforced with edges always referencing kept nodes (UAT2-007).
  - M2-D3 targeted snippets: source is opened only at Code Index
    locations (UAT2-008); unreadable sources degrade to uncertainties.
  - M2-D4 context-read metrics embedded in every pack (elements,
    relations, symbols, snippets, source_lines, context_reads — the
    counter the >=50%-fewer-reads target will be measured against).
  - Compilation is read-only (the world snapshot is untouched) and
    deterministic for identical inputs.
  - CLI `context` with budget overrides; 21 new tests (147 total).
- **V2 Phase C (M2-C1…C4) — Evidence → Architecture
  (`archskillkit.promotion`)**: the deterministic promotion pipeline from
  the Code Index into the Architecture World, i.e. the vertical slice of
  docs/v2/23 (scan edge → Observation → Claim → ArchitectureElement):
  - M2-C1 `ingest_scan`: every evidence edge becomes an Observation
    backed by an Evidence object; idempotent on the provenance tuples.
  - M2-C2 claim lifecycle: one traceable claim per observation
    (`derived_from` + evidence refs); deterministic evaluation links
    same-subject/predicate-different-object contradictions and never
    promotes them (UAT2-006); DETECTED/high claims auto-accept with
    resolvable evidence, INFERRED claims require explicit `accept_claim`
    which refuses unevidenced or contradicted claims.
  - M2-C3 `realize_architecture`: accepted claims map to
    architecture elements (component/external_system/topic/datastore per
    docs/v2/04 categories) and typed relations (exposes/consumes/
    depends_on…) carrying their evidence ids — UAT2-005 holds by
    construction; idempotent.
  - M2-C4 `review`: deterministic reviewer persisting `finding` objects
    (unsupported_claim, contradiction, missing_evidence) plus an
    append-only `review` audit object.
  - New `arch-model` pack (architecture elements + 8 typed relations);
    `arch-core` pack gains finding/review types (v0.2.0).
  - CLI `discover` and `review`; 22 new tests (126 total) including the
    end-to-end slice over the real Kotlin scan with replay verification
    after every mutation.
- **V2 Phase B (M2-B1…B4) — Code Index (`archskillkit.codeindex`)**: the
  deterministic, regenerable `code.sqlite` Evidence Graph per project
  (docs/v2/05):
  - M2-B1 schema: files / symbols / edges with scan provenance,
    `scan_run_id` atomic replace per run, schema-version guard, FTS5
    symbol search (LIKE fallback).
  - M2-B2 ast-grep ingestion: outline NDJSON → files + symbols (kind
    from rule id, 1-based lines, paths relativized to the scan root).
  - M2-B3 Semgrep ingestion: matches → EXPOSES/CONSUMES/USES edges from
    the containing symbol to typed pseudo-symbols (endpoint, topic,
    datastore, http_client); container resolution is nearest-declaration
    within ±2 lines preferring functions; unknown check_ids and orphan
    matches become warnings, never errors.
  - M2-B4 query API: `search_symbol` (prefix FTS), `resolve`
    (id / qualified name / `path::name` / bare unique name with
    ambiguity candidates), `incoming`/`outgoing`, bounded
    `neighborhood`, shortest `path`, transitive `impact`.
  - CLI: `ingest-code`, `index-stats`, `search-code`.
  - 43 new tests (104 total) against REAL scanner payloads captured from
    the pinned V1 toolchain (fixtures normalized to a virtual scan
    root), covering idempotent re-ingest, regenerable determinism,
    atomic failure, isolation, a 1k-symbol ring scale sanity and
    repository cleanliness.
- **V2.2 Phase P0 — projection foundation (`archskillkit.projections`)**:
  `VisualIntent` schema (8 intent types, docs/v2/26), `ProjectionAdapter`
  protocol with `ProjectionContext`/`ProjectionResult` (results always
  carry their source snapshot), projection metadata + lifecycle states
  (requested…superseded, stale/manual-edit flags) and the deterministic
  `ProjectionRouter` with per-intent preference table and compatible
  user override (P0 exit: one intent routes deterministically; 22 new
  tests).
- **V2.2 design package — Projection Applications** (extends the V2
  projection layer without touching V2.1 decisions; spec docs 24–43 in
  `docs/v2/` plus the V2.1/V2.2 spec changelogs alongside them):
  - ADR-0026…0031: VisualIntent + Projection Router, draw.io as the
    general technical projection, JSON Canvas for knowledge maps, GraphML
    as the consumer-neutral graph exchange (Cytoscape/Gephi/yEd consume
    the file — no per-app adapters), one-way projections in V2.2, and no
    own visualization UI.
  - `design/projections/` example payloads (visual-intent,
    projection-result) and `design/schemas/projection-metadata.yaml`
    (source revision, status, staleness, manual-edit flag).
  - `design/packs/arch-projections.md` now describes the generic
    Projection Layer (adapters: likec4, arrows, drawio, jsoncanvas,
    graphml; router consumes VisualIntent).
  - Skill references `v2.2-projection-policy.md` and
    `v2.2-visual-intent-examples.md`, wired into `SKILL.md`.
- **V2 Phase A (M2-A1…A3) — Python domain core (`python/`)**: the
  `archskillkit` package (requires-python >= 3.11, dependency: ActiveGraph
  >= 1.10) delivers the first three V2 milestones:
  - M2-A1 package skeleton with pyproject, console script and the
    `arch-core` pack entry point.
  - M2-A2 domain ontology as the `arch-core` ActiveGraph pack — object
    types `project`, `scan_run`, `observation`, `evidence`, `claim` with
    schemas faithful to `design/schemas/*.yaml`, plus the seven arch-core
    relation types (endpoints pinned where the design pins them).
  - M2-A3 event-sourced Architecture World per project
    (`<workspace>/activegraph.sqlite`): mutations are events, state is a
    pure projection, `replay-verify` proves the log reproduces current
    state (H2-1, UAT2-004); project isolation via per-project stores
    (UAT2-018); repository stays untouched (UAT-001).
  - Identity/path resolution ported 1:1 from the V1 bash helpers —
    bash and Python resolve the same project id (locked by cross-language
    parity tests).
  - Facade CLI `python -m archskillkit init|record-observation|state|replay-verify`.
  - Test infrastructure: 40 pytest tests (matrix 3.12/3.14) and 4 BATS
    seam tests sharing the existing XDG sandbox helpers.
- **V2 design package — ActiveGraph evolution** (mergeable spec over V1,
  kept as the active roadmap; V1 remains the baseline):
  - `docs/v2/` — full V2 specification (two-graph model: regenerable
    `code.sqlite` Evidence Graph + event-sourced ActiveGraph Architecture
    World; Context Compiler; reactive behaviors; drift; fork/diff; UAT and
    spike catalogs; Python-only technology policy).
  - ADR-0013…0025: Python + ActiveGraph as the V2 runtime, Event Log as
    source of truth, LikeC4/Arrows as projections, SQLite code index,
    Context Compiler as central capability, drift before LLM, ActiveGraph
    encapsulated behind the domain, and the definitive Python-only stack
    (ADR-0023 explicitly Rejected — no own Go line).
  - `design/` — initial pack definitions (arch-core, arch-model, arch-code,
    arch-projections) and YAML schemas (observation, architecture-claim,
    context-pack).
  - Skill references `v2-activegraph-workflow.md` and
    `v2-reasoning-policy.md`, plus a V2 roadmap pointer in `SKILL.md`.
- `report.sh`: organized per-project report (`reports/index.md`) with
  evidence summary, mermaid diagrams derived from the arrows-v1 views
  (render natively on GitHub), LikeC4 model validation status and the
  commands to explore the model live (`--serve`).
- `projects.sh`: registry index listing every registered project with its
  latest run outcome.

### Changed

- Context compiler metrics now separate compiler calls from source file
  reads (`compiler_calls`, `source_file_reads`, `source_bytes_read`;
  `context_reads` kept as a compatibility alias).
- ADR-0005 marked **Superseded by ADR-0015 and ADR-0016** — it remains the
  valid baseline for the V1 pipeline; in V2 the LikeC4 canonical model
  becomes a projection of the Architecture World.
- README(s) and `docs/17-roadmap.md` now present V1 as the shipped baseline
  and V2 as the active evolution; the V1 specification is preserved
  unchanged (no history rewrites).

## [0.1.0] - 2026-08-31

First working vertical slice: from any registered repository to validated
architecture evidence and projections, without writing a single file into
the analyzed repository.

### Added

- External XDG workspace resolver with project registry, stable project ids
  (`<name>-<hash>`), remote-based move/rename reconciliation and the
  `ARCH_SKILLKIT_HOME` override.
- Run manifest lifecycle (start/record/finish) with tool versions, scanner
  list, warnings and aggregate status.
- Doctor: environment verification (git, jq, mise, pinned pipeline tools),
  resolved roots, permissions and optional per-project build tools.
- Deterministic scanning pipeline under a single orchestrated run:
  - ast-grep structural outline (Rust, Kotlin, TypeScript),
  - Semgrep architecture rule pack (Spring endpoints/messaging/persistence,
    express endpoints, actix endpoints, reqwest clients),
  - build-system metadata (cargo metadata, raw package.json; Gradle/Maven
    detection only — their build scripts are never executed).
- Repository-clean guarantees: `git status` untouched (UAT-001), cargo
  metadata resolved on a throwaway snapshot when no lockfile exists.
- LikeC4 vertical slice: pinned likec4, golden model template, read-only
  validation (`model-validate.sh`) and conservative update semantics —
  reruns never touch `likec4/` or `knowledge/` (UAT-006).
- Arrows projections derived from evidence with the `arch-skillkit/arrows-v1`
  schema: overview, dependencies, endpoints, messaging, data-access views
  generated only when their evidence exists.
- Agent role references: Scanner, Discovery, Modeler, Arrows, Review — with
  handoff contracts (`reports/inventory.md`, `reports/review-findings.md`,
  `knowledge/assumptions.yaml`).
- Documentation CI (markdownlint, shellcheck, MANIFEST sync) and a 56-test
  BATS suite covering UAT-001/002/003 and failure semantics.
- Pinned toolchain via mise: ast-grep 0.45.2, semgrep 1.175.0, likec4 1.59.2.
