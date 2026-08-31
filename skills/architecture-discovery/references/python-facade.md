# Python Facade — CLI Reference

`python -m archskillkit` is the canonical entry point of the V2
application (requires-python >= 3.11, ActiveGraph runtime). Every
command is read-only towards the analyzed repository and writes to the
external XDG workspace. Exit codes: `0` ok, `1` runtime/world error,
`2` argument or precondition failure.

## World lifecycle

| Command | Effect |
|---|---|
| `init --repo R` | Resolve project id, create workspace, anchor the Project object. Prints JSON `{project_id, workspace, activegraph_db}`. |
| `state --repo R` | Full world snapshot as JSON (counts, objects, relations). |
| `replay-verify --repo R` | Prove the event log reproduces current state (H2-1). Non-zero on divergence. |
| `record-observation --repo R --payload F` | Add an Observation (JSON per `design/schemas/observation.yaml`). |

## Code Index (Graph A)

| Command | Effect |
|---|---|
| `ingest-code --repo R [--astgrep F] [--semgrep F] --run-id ID` | Ingest scanner payloads into `code.sqlite`. Atomic per run id; re-ingesting the same id replaces it. |
| `index-stats --repo R` | Files/symbols/edges counts by kind. |
| `search-code --repo R QUERY` | FTS prefix search over symbols. |

## Promotion pipeline (Graph A → Graph B)

| Command | Effect |
|---|---|
| `discover --repo R --run-id ID` | Full vertical: scan edges → Observations → Claims → architecture → review. Idempotent. |
| `review --repo R` | Deterministic findings: unsupported claims, contradictions, missing evidence. |
| `drift --repo R` | Boundary-rule violations + stale-evidence detection. |

## Projections

| Command | Effect |
|---|---|
| `project --repo R [--format likec4\|arrows\|both] [--force]` | Render the world to `likec4/model.c4` and `arrows/architecture.arrows` with metadata sidecars. Refuses manually-modified artifacts without `--force`. |
| `context --repo R --goal G [--subject S] [--max-nodes N --max-edges N --max-lines L]` | Budgeted ContextPack: ranked elements/relations, code facts, evidence, snippets, uncertainties, context-read metrics. |

## Proposals (fork/diff)

| Command | Effect |
|---|---|
| `fork --repo R --name NAME` | Branch the world into run `proposal-NAME` (UAT2-012 isolation). |
| `diff --repo R --name NAME` | Structural diff vs the world (adds/removes, confidence, evidence, findings). |
| `promote --repo R --name NAME --approved-by ACTOR` | Apply an approved proposal; refused without approval (UAT2-014). |
| `reject-proposal --repo R --name NAME --actor ACTOR` | Reject, keep the scenario browsable. |

## Programmatic use

The CLI is a thin facade over the library:

```python
from archskillkit.world import ArchitectureWorld        # event-sourced world
from archskillkit.codeindex import CodeIndex             # regenerable code.sqlite
from archskillkit.promotion import discover, review      # deterministic pipeline
from archskillkit.context import ContextCompiler, Budget # budgeted ContextPacks
from archskillkit.proposals import structural_diff, promote
from archskillkit.projections.writer import project_to_workspace, is_stale
```

Pack schemas (validation happens in every session):
`archskillkit.packs.arch_core` (project, scan_run, observation, evidence,
claim, finding, review) and `archskillkit.packs.arch_model`
(architecture_element, architecture_rule, proposal + typed relations).
