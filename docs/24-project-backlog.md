# Backlog inicial priorizado

## Must

- [x] Public repository skeleton
- [x] LICENSE
- [x] Agent Skill skeleton
- [x] XDG workspace resolver
- [x] project registry
- [x] run manifest
- [x] mise toolchain
- [x] ast-grep baseline
- [x] Semgrep rule pack
- [x] Rust build metadata
- [x] discovery prompt
- [x] modeler prompt
- [x] reviewer prompt
- [x] LikeC4 validation
- [x] Arrows basic generation
- [x] repository-clean UAT
- [x] fixtures
- [x] release workflow

## Should

- [ ] Kotlin/Java pack
- [ ] TypeScript pack
- [ ] override schema
- [ ] report template
- [ ] install via GitHub Skills
- [ ] install via skills.sh
- [ ] uninstall/update docs
- [ ] benchmark agent reads

## Could

- [ ] workspace Git init opt-in
- [ ] static HTML report
- [ ] diagram export helpers
- [ ] OpenAPI sensor
- [ ] Kubernetes sensor
- [ ] Terraform sensor

## Deferred / requires trigger

- [ ] SCIP
- [ ] normalizer
- [ ] Rust CLI
- [ ] incremental engine
- [ ] CodeQL
- [ ] runtime OTEL
- [ ] graph DB
- [ ] MCP
- [ ] UI

## Phase 7 findings backlog (real-world validation, 2026-08-31)

Found running the full vertical on a real framework-free Kotlin repository
(pipeline-kotlin, 505 .kt files). Feeds the Phase 8 checkpoint.

- [ ] P-1 — concurrency-aware cleanliness assertion (UAT-001 snapshot diff
      produces false alarms when the user develops during the scan)
- [ ] P-2 — record tool usage per scanned system, not tool availability
- [ ] P-3 — static Gradle dependency extraction (no execution) to derive
      module graphs as scanner evidence instead of targeted reads
- [ ] P-4 — language pack: framework-less Kotlin outline-only profile
- [x] P-5 — organized viewing layer: report.sh (mermaid index + model
      status + live-view commands) and projects.sh (registry index)
- [ ] P-6 — arrows.app import adapter for arch-skillkit/arrows-v1
- [ ] P-7 — endpoint labels from route paths (blocked: semgrep OSS gates
      snippets/metavariables; revisit rule design or agent enrichment)
- [ ] P-8 — baseline comparison for UAT-012 (agent reads with vs without
      ArchSkillKit) on a real repository
