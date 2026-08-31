# Task Recipes

Exact command sequences per routing-table context. `<run>` is a run id
(`run-1`, `scan-2026-09-01`, …). Run from the analyzed repository root
with the ArchSkillKit skill on PATH; `python -m archskillkit` requires
`pip install -e <skill>/python` (doctor tells you).

## bootstrap — cold-start analysis of a repository

```bash
python -m archskillkit init --repo .                       # workspace + project id
python -m archskillkit ingest-code --repo . \
  --astgrep evidence.json --semgrep patterns.json --run-id <run>
# evidence.json / patterns.json come from scripts/scan.sh (V1) or the
# scanner role; see architecture-discovery/references/scanning.md
python -m archskillkit discover --repo . --run-id <run>    # facts -> architecture
python -m archskillkit review --repo .                     # unsupported claims, contradictions
python -m archskillkit drift --repo .                      # boundary violations (with rules)
python -m archskillkit project --repo .                    # likec4/model.c4 + arrows/*.arrows
python -m archskillkit replay-verify --repo .              # log -> state proof
git status --porcelain                                     # must be empty diff vs start
```

Deliverable: counts from `discover` (observations, claims, elements,
relations, findings), `review`/`drift` findings, artifact paths.

## explain — "how does X work?" / backend questions

```bash
python -m archskillkit search-code --repo . "<X>"          # locate symbols
python -m archskillkit context --repo . \
  --goal "explain <X>" --subject <X> --max-nodes 20        # budgeted pack + snippets
python -m archskillkit state --repo .                      # only if architecture-level view needed
```

Snippets inside the ContextPack are the ONLY source lines to open, and
they are already resolved to locations. If the Code Index cannot find
`<X>`, switch to the `ast-grep` skill to author a structural query, then
re-ingest.

## diagram — visualization requests

1. Classify the intent (`v2.2-projection-policy`): architecture → LikeC4,
   exploration → Arrows, embedded-in-Markdown → mermaid, knowledge map →
   JSON Canvas (P2), large graph → GraphML (P3), editable technical →
   draw.io (P4).
2. For mermaid: pull data with `state` / `context`, render per the
   `mermaid` skill, embed in `reports/index.md` with sanitized ids.
3. For projections: `python -m archskillkit project --repo .` (writes
   `likec4/model.c4` + `arrows/architecture.arrows` with metadata
   sidecars). If a projection was manually modified, it refuses — that
   is UAT-P12 protection; use `--force` only on explicit user consent.

## watch — architecture health check

```bash
python -m archskillkit review --repo .
python -m archskillkit drift --repo .
python -m archskillkit replay-verify --repo .
```

Declare new boundary rules before judging drift:
`world.record_architecture_rule(...)` (see `docs/v2/09` for rule kinds).
Re-run after code changes; `drift` reports `stale_evidence` when the
index no longer backs accepted architecture.

## proposal — "what if we changed X → Y?"

```bash
python -m archskillkit fork --repo . --name async-payments
# mutate ONLY the fork (agent work): add/patch elements and relations in
# run proposal-async-payments, then register the paperwork:
#   fork.record_proposal("async-payments", rationale="...")
python -m archskillkit diff --repo . --name async-payments      # structural diff
python -m archskillkit promote --repo . --name async-payments \
  --approved-by <human>            # only after the human approves the diff
python -m archskillkit reject-proposal --repo . --name async-payments \
  --actor <human>                  # keeps the scenario, refuses future promotion
```

Never promote without an explicit human approver (UAT2-014). Main stays
byte-identical until promotion (UAT2-012).

## extend-detection — teach the scanners a new pattern

Delegate to the `semgrep` skill (rule authoring, test-first) and/or the
`ast-grep` skill (structural queries). Come back to the pipeline:
`ingest-code` → `discover` → `review`. Rule id families determine how
facts map to architecture edges — follow
`architecture-discovery/references/scanner-output-interpretation.md`.

## develop — extend ArchSkillKit itself

Read `docs/v2/23-implementation-sequence.md` for the vertical order and
`docs/v2/20-backlog-v2.md` for Must/Should. TDD is mandatory: pytest for
the Python core (`python/tests/`), BATS for script seams (`tests/`).
Repository-clean and evidence-first invariants apply to the toolkit's
own development too.
