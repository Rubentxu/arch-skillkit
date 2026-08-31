# Changelog

All notable changes to ArchSkillKit are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning is
SemVer (docs/05): MAJOR breaks workspace/evidence/Skill contracts, MINOR
adds compatible capabilities, PATCH covers compatible rules, prompts and
fixes.

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
