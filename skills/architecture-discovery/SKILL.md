---
name: architecture-discovery
description: >
  Discover, model and review software architecture without modifying the
  source repository. Prefer deterministic evidence from ast-grep, Semgrep
  and build metadata; generate LikeC4 as the canonical architecture model
  and Arrows as exploratory graph views. Store all generated assets in an
  external XDG workspace.
---

# Architecture Discovery

> **Orchestration**: if you are deciding HOW to approach a task (what to
> run, in which order, what to load), start from the `arch-orchestrator`
> skill — it routes tasks to phases, skills and commands with minimum
> context. This skill is the deep pipeline reference it delegates to.
> The V2 Python commands are catalogued in
> `references/python-facade.md`.

## Non-negotiable rules

1. Treat the source repository as read-only. Verify with `git status`
   before and after any work: it must be identical (UAT-001).
2. Never create ArchSkillKit assets inside the repository — everything
   goes to the external XDG workspace resolved by the scripts.
3. Prefer deterministic scanners before opening source files with the
   LLM. Every source read must target a location already resolved by a
   scanner or the Code Index (UAT2-008).
4. Classify knowledge as DETECTED, INFERRED or DECLARED, with
   high | medium | low confidence.
5. Do not promote low-confidence or contradicted claims into the
   architecture — contradictions block silent promotion (UAT2-006).
6. Preserve evidence and provenance: automatic high-confidence
   relations must carry evidence links (UAT2-005).
7. Review the final model for unsupported relationships before handing
   it over.

## Workflow

Run the pipeline through the scripts; each step degrades gracefully
with actionable errors.

1. **Resolve the workspace**: `scripts/workspace.sh --repo <path>` —
   detects the repo, computes the stable project id, registers it.
2. **Check the environment**: `scripts/doctor.sh` — git, jq, mise and
   the pinned scanners; it tells you exactly what to run on first use
   (`mise install -C skills/architecture-discovery/runtime`).
3. **Scan** (deterministic, no LLM): `scripts/scan.sh --repo <path>`
   runs ast-grep outline, Semgrep patterns and build metadata in one
   run manifest. Read `references/scanning.md` for per-scanner details.
4. **Interpret**: read `references/scanner-output-interpretation.md` to
   map raw payloads to meaning. Query facts without re-scanning or
   reading source: `search-code`, `index-stats`, `context`.
5. **Discover** (V2): `python -m archskillkit discover --repo <path>
   --run-id <run>` turns scan edges into Observations, Claims and the
   architecture graph. Read `references/discovery.md`.
6. **Review** (deterministic): `python -m archskillkit review` and
   `python -m archskillkit drift` surface unsupported claims,
   contradictions, missing evidence and boundary drift with no LLM.
7. **Model and project**: generate LikeC4 + Arrows with
   `python -m archskillkit project --repo <path>` (validated against
   the pinned likec4), or follow `references/likec4.md` /
   `references/arrows.md` for the V1 flow.
8. **Report**: `scripts/report.sh --repo <path>` builds
   `reports/index.md` with evidence summary and mermaid diagrams; add
   hand-crafted diagrams with the `mermaid` skill.

## Skills this toolkit composes with

Read these when the task goes beyond the scripts:

- **`ast-grep` skill** — writing structural code queries and rule
  debugging (`--debug-query`, `stopBy`, metavariables). Use when the
  rule pack misses a pattern for a backend framework.
- **`semgrep` skill** — running scans and authoring detection rules
  (taint mode, pattern operators, test-first rule workflow). Use when
  extending the architecture pack to new frameworks.
- **`mermaid` skill** — embedded diagrams for reports with official
  syntax references for 23+ diagram types. Use for human-scale
  diagrams; for curated architecture prefer LikeC4.

## Role routing

- Scanner — run the deterministic pipeline: read `references/scanning.md`.
- Discovery — interpret evidence into an inventory: read `references/discovery.md`.
- Modeler — keep the LikeC4 model valid and conservative: read `references/likec4.md`.
- Arrows — derive exploratory graph views: read `references/arrows.md`.
- Review — audit claims, evidence and repository cleanliness: read `references/review.md`.

## Policies

- Architecture policy: read `references/modeling-policy.md`.
- Evidence policy: read `references/evidence-policy.md`.
- Scanner output formats and traps: read
  `references/scanner-output-interpretation.md`.

## V2 roadmap (ActiveGraph)

The V2 evolution replaces the canonical LikeC4 model with an event-sourced
Architecture World (ActiveGraph) plus a deterministic Code Index (SQLite);
LikeC4 and Arrows become projections. The V1 workflow above remains the
baseline. For the V2 pipeline and reasoning policy read:

- `references/v2-activegraph-workflow.md`
- `references/v2-reasoning-policy.md`

V2.2 adds a projection layer (VisualIntent → Projection Router → LikeC4 /
Arrows / draw.io / JSON Canvas / GraphML). For the projection policy and
intent examples read:

- `references/v2.2-projection-policy.md`
- `references/v2.2-visual-intent-examples.md`
