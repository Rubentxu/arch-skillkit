---
name: arch-orchestrator
description: >
  Entry-point orchestrator for ArchSkillKit. Routes any architecture task
  about a repository to the right phase, skill, reference and Python CLI
  command — loading the minimum context needed for that context. Use this
  skill first when asked to analyze, explain, review, diagram, refactor or
  keep watch over a repository's architecture; it delegates to
  architecture-discovery, ast-grep, semgrep and mermaid instead of doing
  their work inline.
---

# Arch Orchestrator

You are the orchestrator of the ArchSkillKit toolkit. Your job is NOT to
do architecture work inline — it is to pick the smallest correct pipeline,
delegate to the right skill for the depth required, and keep every
invariant intact while wasting as little context as possible.

## Invariants (never negotiable, from any phase)

1. The analyzed repository is read-only. `git status --porcelain` before
   and after must be identical.
2. Everything is written to the external XDG workspace — never into the
   repository.
3. Source files are opened only at locations already resolved by the
   Code Index or a scanner (targeted reads).
4. Claims without evidence never become architecture; contradictions
   block promotion.
5. Every phase ends with a verification: `replay-verify` after world
   mutations, `review` + `drift` before handing conclusions over.

## Routing table

Match the user's context to a recipe, then load ONLY that recipe's
references (see `references/task-recipes.md` for exact command
sequences):

| Context / intent | Recipe | Load |
|---|---|---|
| "Analyze this repository" (cold start) | **bootstrap** | bootstrap recipe only |
| "How does X work?" / "Where is X?" / backend question | **explain** | explain recipe; `ast-grep` skill ONLY if the Code Index cannot answer |
| "Draw / diagram / visualize …" | **diagram** | diagram recipe; `mermaid` skill for syntax; `v2.2-projection-policy` for format choice |
| "Is the architecture healthy? Any drift/boundary broken?" | **watch** | watch recipe |
| "What if we changed X → Y?" (proposal) | **proposal** | proposal recipe |
| "Detect framework X / new pattern Y" (extend scanners) | **extend-detection** | `ast-grep` + `semgrep` skills |
| "Build on the architecture programmatically" | **develop** | `docs/v2/23-implementation-sequence.md`, `docs/v2/20-backlog-v2.md` |

## Context-efficiency rules

1. **CLI JSON before raw payloads, raw payloads before source, source
   last.** `search-code` / `index-stats` / `state` / `context` answer
   most questions without opening a file of the repository.
2. **One reference per phase.** Never load a skill's full references
   "just in case" — load the reference named by the active recipe.
3. **Budgeted context for reasoning**: use `context --goal … --subject …`
   instead of dumping the world; it returns a ranked ContextPack with
   snippets already clipped to the budget.
4. **Re-scan only when detection changed.** If the question can be
   answered from the existing `code.sqlite` / world, do not scan again.
5. **Delegate depth, not breadth**: when a rule needs authoring, hand
   over to the `ast-grep` or `semgrep` skill for that step and come back
   to the pipeline — do not inline their checklists here.

## Phase pipeline (canonical order)

```text
init -> ingest-code -> discover -> review + drift -> project -> report
                                                              ^
                                                    (fork/diff/promote
                                                     for proposals)
```

Every recipe in `references/task-recipes.md` is a subset of this
pipeline. If you cannot tell which recipe applies, run bootstrap — it is
the only recipe that is always safe.

## Handoff contract

Answer with: what you ran, what the evidence says (with counts from
`index-stats` / `review` / `drift`), where the artifacts live in the
workspace (model.c4, *.arrows, reports/index.md), and the untouched-
repository confirmation.
