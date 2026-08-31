# Changelog

All notable changes to ArchSkillKit are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning is
SemVer (docs/05): MAJOR breaks workspace/evidence/Skill contracts, MINOR
adds compatible capabilities, PATCH covers compatible rules, prompts and
fixes.

## [Unreleased]

### Added

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
