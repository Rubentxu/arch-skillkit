# Audit Report — M6 Context & Agent Efficiency Closure

## Status

**Accepted** — M6 acceptance gates (`SESSION-STALE-001`, `CTX-BUDGET-001`)
are **PASS** as of v0.13.2. M6 milestone is **CLOSED**.

## Context

V2.5 roadmap Milestone M6 ("Context & Agent Efficiency",
`docs/v2/83-v2.5-roadmap.md`) declares three acceptance gates in
`docs/v2/84-v2.5-milestones.md`:

- `CTX-BUDGET-001` — context budget violations == 0
- `CTX-GROUNDING-001` — not in gate catalog (see ADR-0048)
- `SESSION-STALE-001` — stale session detection rate == 1.0

ADR-0048 (audit-only cycle) declared:

> `CTX-BUDGET-001` PARTIAL (3 test failures are environment hygiene
> issues — `No module named archskillkit` in subprocess PYTHONPATH +
> Kotlin fixture drift; not code gaps).

After v0.13.1 (M5b closure, PR #12) fixed two of the three failures
(PYTHONPATH propagation in `_sandbox_env`), only one test failure
remained: `test_subject_narrows_the_pack` in `tests/test_context.py`.
On inspection it was not environment hygiene — it was a **real bug**
in `ContextCompiler.compile()` that had been masked by an outdated
fixture-name assertion.

## Bug discovered

### Test failure detail

```
tests/test_context.py::TestSubjectResolution::test_subject_narrows_the_pack
AssertionError: assert 'endpoint@11' in
    {'kotlin-spring/src/main/kotlin/demo/infra/Http.kt::getPayment'}
```

The world contains two architecture elements per HTTP endpoint
(after `promotion.discover`):

| id | name | kind |
|---|---|---|
| `#17` | `kotlin-spring/.../Http.kt::getPayment` | component |
| `#18` | `endpoint@11` | interface |

They are linked by an `exposes` relation (`#17 --exposes--> #18`).
The test expected both to appear in the pack when `subject="getPayment"`
was passed, plus the `exposes` relation. The compiler returned only `#17`
and no relations.

### Root cause

Two coupled issues in `python/src/archskillkit/context.py::compile()`:

1. **Subject narrowing was too strict.** `_elements_for(subject)`
   returned only elements whose name matched the subject string. The
   neighbour (`#18` `endpoint@11`) does not contain "getPayment" and
   was excluded from `elements`.

2. **Relation filter required both endpoints in `kept`.** Even when
   `_relations_touching(seed_ids)` collected the `#17 --exposes--> #18`
   edge, the later filter
   `if r["source"] in kept and r["target"] in kept` dropped it because
   `#18` was not in `kept` (only `#17` was).

The combination made the test fail: subject narrow left one endpoint
out of the pack, then the relation filter dropped the connecting edge.

This bug existed since v2.0 (`35dfe0e feat(v2): Context Compiler`).
It was masked because the test assertion used the short name
`"endpoint@11"`, which the `_elements_for` filter could not match —
so the test had been failing for the same reason since the
`promotion.discover` rename to qualified_name.

## Fix

Single change in `compile()` (`python/src/archskillkit/context.py`,
lines 113–131):

After `_relations_touching(seed_ids)`, expand `elements` with the
immediate graph neighbours of the seed set **when** `subject` is
provided. This keeps the relation subgraph closed: the `component →
interface` pair stays together, and the `exposes` edge survives the
final `and`-filter because both endpoints are now in `kept`.

```python
if subject and relations:
    neighbour_ids = (
        ({r["source"] for r in relations} | {r["target"] for r in relations})
        - seed_ids
    )
    if neighbour_ids:
        present = {e["id"] for e in elements}
        elements = list(elements) + [
            obj for obj in self.world.find_objects("architecture_element")
            if obj["id"] in neighbour_ids and obj["id"] not in present
        ]
```

Properties of the fix:

- **Localised.** ~15 lines in one function. No new types, no new
  imports, no schema changes.
- **Lazy.** Only runs when `subject` is provided AND there are
  relations touching the seeds. Full-world compiles (no subject)
  pay zero cost.
- **Idempotent.** `present` set deduplicates; if the neighbour is
  already in `elements` (e.g. subject matched both endpoints) it is
  not added twice.
- **Budget-respecting.** The expansion happens before
  `elements[:budget.max_nodes]`, so the budget still applies.

## Evidence

### `CTX-BUDGET-001` (PASS)

The exact command ADR-0048 used to declare the gate PARTIAL:

```bash
cd python && .venv/bin/python -m pytest \
    tests/test_context.py tests/test_cli.py \
    -k 'budget or context' -v
```

Result after the fix:

```
27 passed, 17 deselected in 9.55s
```

Was: `3 failed, 24 passed`. Now: `27 passed, 0 failed`.

### Targeted files (M5b + M6)

```bash
cd python && .venv/bin/python -m pytest \
    tests/test_context.py tests/test_cli.py tests/test_codegraph_port.py -q
```

Result: `76 passed in 40.70s`. No regression in M5b or M6 surfaces.

### Architecture gate

```bash
mise run verify:architecture   # EXIT=0
```

### ARC-010 unchanged

`0 findings` (was `0 findings` at v0.13.1). The new code path
(`world.find_objects(...)` for neighbours) reads the same architecture
graph the verifier inspects; no new forbidden imports or dependencies.

## Decision

| Gate | Status (ADR-0048) | Status (v0.13.2) |
|---|---|---|
| `CTX-BUDGET-001` | PARTIAL (3 failed) | **PASS (27/27)** |
| `CTX-GROUNDING-001` | not in catalog | not in catalog (unchanged) |
| `SESSION-STALE-001` | PASS | **PASS** (unchanged) |

`CTX-GROUNDING-001` remains a design item in
`docs/v2/87-v2.5-backlog-deferred.md`. It requires an ADR that defines
what counts as "grounding evidence" in a context pack (citations,
provenance ratios, etc.) before any gate can be written. Out of scope
for this audit-only + bugfix cycle.

**M6 is CLOSED at v0.13.2.** The two M6 gates that have a
deterministic implementation both pass.

## Consequences

- The roadmap is now honest for M0–M6. M7 and M8 remain PARTIAL /
  DEFERRED per ADR-0048.
- The fix does not change any public API, schema, or CLI surface.
  Existing full-world compiles behave identically because the new
  branch only runs when `subject is not None`.
- `test_subject_narrows_the_pack` was the canary for this bug. With
  it green, the subject-narrow path is exercised end-to-end in CI.

## Verification commands

```bash
# CTX-BUDGET-001 evidence (the gate metric)
cd python && .venv/bin/python -m pytest \
    tests/test_context.py tests/test_cli.py -k 'budget or context' -v

# Subject narrow regression (now passes)
cd python && .venv/bin/python -m pytest \
    tests/test_context.py::TestSubjectResolution -v

# Architecture conformance
mise run verify:architecture
```
