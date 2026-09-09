# ADR-0051 — CTX-GROUNDING-001 Gate Definition

## Status

**Accepted** — `CTX-GROUNDING-001` is now defined, registered in
`docs/v2/verification/quality-gates.json`, and exercised by a regression
test. M6 is fully closed.

## Context

V2.5 roadmap Milestone M6 ("Context & Agent Efficiency",
`docs/v2/83-v2.5-roadmap.md`) declares three acceptance gates in
`docs/v2/84-v2.5-milestones.md`:

- `CTX-BUDGET-001` — context budget violations == 0 (CLOSED at v0.13.2, ADR-0049)
- `CTX-GROUNDING-001` — grounding ratio gate (this ADR)
- `SESSION-STALE-001` — stale session detection rate == 1.0 (PASS at v0.13.0)

ADR-0048 and ADR-0049 both flagged `CTX-GROUNDING-001` as "not in gate
catalog" and deferred its definition to a design cycle. This ADR
closes that deferral.

## Definition

**Metric**: `context_grounding_ratio`. This is the
`evidence_density` field already exposed by `ContextCompiler.compile()`
on the `ContextPack` model:

```python
# python/src/archskillkit/context.py:179-184
evidence_backed = sum(
    1 for r in relations if (r.get("data") or {}).get("evidence_ids"))
evidence_density = (evidence_backed / len(relations)
                    if relations else 0.0)
# ... and exposed at:
# python/src/archskillkit/context.py:239
pack.metrics["evidence_density"] = evidence_density
```

The metric is the ratio of relations in a context pack that carry at
least one `evidence_ids` reference, divided by the total number of
relations in the pack. It measures how much of the served graph is
traceable to scanner-detected evidence.

**Operator**: `>=`

**Threshold**: `0.5` (50%)

**Class**: `BLOCKING`

**Scope**: applies to all packs compiled by `ContextCompiler.compile()`,
with the empty-relations exemption documented in the spec.

## Why 0.5?

Empirically observed on the Kotlin demo fixture (`tests/fixtures/`
NDJSON payloads committed at v0.13.0):

| Scenario | Relations | Evidence-backed | Ratio |
|---|---|---|---|
| `compile(subject="getPayment")` | 1 | 1 | 1.00 |
| `compile(goal="overview")` | 5 | 5 | 1.00 |

The observed ratio is 1.00 because every `promotion.discover`-produced
relation carries a non-empty `evidence_ids` (the semgrep rule metadata
populates it at ingestion time, `codeindex.py:568-583`).

The 0.5 threshold provides 50% margin to catch regressions like:

- `evidence_ids` accidentally dropped during a refactor of
  `codeindex.py` (would drop ratio to 0.0 — clear regression).
- A new scanner rule added without metadata (would drop ratio
  proportionally — easy to detect).
- Coverage gaps in the in-tree fixtures (false positives easy to triage).

A higher threshold (e.g. 0.8) would catch no current regression and
only add friction. A lower threshold (e.g. 0.1) would mask the kind of
regression this gate exists to detect.

## Decision

Add the gate entry to `docs/v2/verification/quality-gates.json`:

```json
{
  "class": "BLOCKING",
  "id": "CTX-GROUNDING-001",
  "metric": "context_grounding_ratio",
  "milestone": "M6",
  "operator": ">=",
  "threshold": 0.5
}
```

Add a regression test in `python/tests/test_context.py` that:

- compiles a pack from the Kotlin demo fixture with `subject="getPayment"`
- asserts `pack.metrics["evidence_density"] >= 0.5`
- asserts `pack.architecture["relations"]` is non-empty

Update `docs/v2/84-v2.5-milestones.md` M6 status to:

> Status: **CLOSED at v0.13.4** — see ADR-0049 + ADR-0051.

## Compatibility

- No public API changes (the metric already existed; the gate is policy).
- No schema changes (gate catalog gains one entry).
- No CLI surface changes.

## Consequences

- M6 milestone is fully closed: all three declared gates pass.
- The threshold is a deliberate policy choice. Future cycles that
  introduce a scanner without `evidence_ids` metadata will be caught
  by this gate as part of the standard test suite.
- The empty-pack exemption means that a project with no relations is
  not penalised. A future enhancement could require at least 1
  relation when the world contains architecture elements, but that
  is a different gate (would belong in M0/M1, not M6).

## Verification commands

```bash
# The metric is already exposed; verify it directly
cd python && .venv/bin/python -c "
from archskillkit.context import ContextCompiler, Budget
# ... setup world + index from fixture ...
pack = ContextCompiler(world, index).compile(
    goal='how does payment exposure work', subject='getPayment')
assert pack.metrics['evidence_density'] >= 0.5
assert len(pack.architecture['relations']) >= 1
print('OK ratio=', pack.metrics['evidence_density'])
"

# The new regression test
cd python && .venv/bin/python -m pytest \
    tests/test_context.py::TestContextGroundingGate -v
```
