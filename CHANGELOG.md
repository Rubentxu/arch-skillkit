# Changelog

All notable changes to ArchSkillKit are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning is
SemVer (docs/05): MAJOR breaks workspace/evidence/Skill contracts, MINOR
adds compatible capabilities, PATCH covers compatible rules, prompts and
fixes.

## [Unreleased]

### Added

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
