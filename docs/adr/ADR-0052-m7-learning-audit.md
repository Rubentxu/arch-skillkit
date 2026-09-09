# ADR-0052 — M7 (Learning) Audit-Only Closure

## Status

**Audit-only closure accepted.** M7 is **PARTIAL by design** at v0.13.5:
the mandatory gate `LEARN-NO-AUTO-ACCEPT-001` PASSes; the deferred gates
`SENSOR-EVAL-001` and `SENSOR-ROI-001` are correctly absent because the
**trigger criteria for closing them are unmet**. This ADR documents what
those trigger criteria are, why they are unmet at v0.13.5, and what
would have to be true before they can be defined.

This ADR closes no gate. It records a finding so that future cycles
can act on it without re-doing the audit.

## Context

V2.5 roadmap Milestone M7 ("Learning Architecture",
`docs/v2/83-v2.5-roadmap.md#m7--learning-architecture`) declares three
acceptance gates in `docs/v2/84-v2.5-milestones.md#m7--learning`:

- `LEARN-NO-AUTO-ACCEPT-001`
- `SENSOR-EVAL-001`
- `SENSOR-ROI-001`

ADR-0048 (M0–M6 closure audit at v0.13.3) declared M7 PARTIAL and
deferred the two non-`LEARN-NO-AUTO-ACCEPT` gates "until a sensor with
measurable LLM cost exists." This ADR verifies that statement against
the v0.13.5 codebase and either confirms or revises it.

## What exists today

The learning path is fully implemented and tested:

| Surface | File | Lines |
|---|---|---|
| `SensorCandidate` model + `evaluate_sensor()` | `python/src/archskillkit/sensor_candidate.py` | 415 |
| `SensorDistiller` (corpus curation) | `python/src/archskillkit/sensor_distiller.py` | 229 |
| `sensors` command (application layer) | `python/src/archskillkit/application/commands/sensors.py` | (sensor promote cmd at L87) |
| `promote-sensor` CLI | `python/src/archskillkit/delivery/cli/promote_sensor.py` | ~180 |
| Tests: `test_sensor_application.py` | `python/tests/test_sensor_application.py` | 106 |
| Tests: `test_sensor_candidate.py` | `python/tests/test_sensor_candidate.py` | 311 |
| Tests: `test_sensor_distiller.py` | `python/tests/test_sensor_distiller.py` | 416 |

The `promote-sensor` CLI requires **explicit `--min-precision` and
`--min-recall` thresholds** (default 0.9/0.9); there is **no auto-accept
path** (`python/src/archskillkit/delivery/cli/promote_sensor.py:129,135`).
The threshold check is enforced via `meets_threshold()`
(`python/src/archskillkit/sensor_candidate.py:142`).

This means `LEARN-NO-AUTO-ACCEPT-001` PASSes by construction: a
sensor cannot be promoted without a human authorising both thresholds.

## What is missing

`SENSOR-EVAL-001` ("sensor evaluation is reproducible and statistically
meaningful") and `SENSOR-ROI-001` ("promoted sensors measurably reduce
LLM calls or tokens") are declared in `84-v2.5-milestones.md` but are
**not in the gate catalog** (`docs/v2/verification/quality-gates.json`,
17 entries as of v0.13.4). Adding them requires:

1. **For `SENSOR-EVAL-001`** — a reproducible evaluation harness:
   - A fixture corpus (positive + negative examples) committed to the
     repo (analogous to `tests/fixtures/`).
   - A measurement surface that exposes precision/recall on that
     corpus.
   - A gate entry that asserts both numbers across all promoted
     sensors.
   - A regression test that fails if the harness reports a regression.

2. **For `SENSOR-ROI-001`** — a cost-measurement surface:
   - A way to count LLM calls/tokens per compilation step
     (currently the compiler only emits the metrics field on
     `ContextPack.metrics`, which is an *output* metric, not an
     *input cost* metric).
   - A counterfactual comparison: "what would the LLM have done
     without this sensor?" — the necessary scaffolding for this
     comparison does not exist.
   - A gate entry that asserts a measurable delta (e.g., "sensor X
     reduces LLM-token spend by ≥N% across the UAT corpus").

Neither scaffolding exists at v0.13.5.

## Trigger criteria

This ADR proposes the following trigger criteria, consistent with
ADR-0048's deferral rationale:

### `SENSOR-EVAL-001` becomes closable when ALL of:

1. At least one `SensorCandidate` has been promoted to a deterministic
   sensor via `archskillkit promote-sensor` and is referenced in
   production scan rules.
2. The promotion process produced evaluation artifacts
   (precision/recall numbers on a fixture corpus) that are committed
   to `tests/fixtures/sensor-evaluation/` or equivalent.
3. The sensor's evaluation result is reproducible across two
   independent runs (deterministic, no clock/randomness dependency).

### `SENSOR-ROI-001` becomes closable when ALL of:

1. `SENSOR-EVAL-001` has been closed (prerequisite — must know what
   the sensor *does* before measuring whether it helps).
2. The compilation pipeline emits LLM call/token counts in a
   machine-readable way (currently absent — see `python/src/archskillkit/context.py:239`
   for the closest existing surface).
3. At least one UAT corpus scenario exists where the sensor fires and
   the resulting pack differs from a no-sensor baseline pack.
4. The token-count delta between sensor-on and sensor-off runs is
   measurable, positive, and statistically significant (≥10% reduction
   across the corpus, no regression on any individual scenario).

### Why these criteria

These criteria are not arbitrary. They reflect what a gate must do to
be meaningful:

- A gate that fires on **no data** is theatre. Hence criterion 1 for
  each — there must be a real artifact to measure.
- A gate that cannot detect regression is theatre. Hence criterion 3
  for `SENSOR-EVAL-001` (determinism) and criterion 4 for
  `SENSOR-ROI-001` (statistical significance).
- A gate with no realistic threshold is theatre. Hence criterion 4 for
  `SENSOR-ROI-001` (≥10%) — set with the same margin philosophy as
  ADR-0051 §"Why 0.5?" (a threshold far enough above noise floor to
  catch regressions, far enough below expected value to avoid
  friction).

## Why the criteria are unmet at v0.13.5

- No promoted sensor has reached production scan rules yet (the
  `promote-sensor` CLI exists, but no historical commit shows it being
  invoked end-to-end against a fixture corpus committed to the repo).
  Verified by `git log --all --oneline | grep promote-sensor` (no hits).
- No `tests/fixtures/sensor-evaluation/` directory exists.
- No LLM call/token counter exists in the compilation pipeline.

## Decision

M7 is **PARTIAL by design**. Do not close it.

- Add an explicit "trigger criteria for closure" section to
  `docs/v2/84-v2.5-milestones.md` M7 status block, citing this ADR.
- Add this ADR to `docs/adr/INDEX.md` if such a file exists;
  otherwise the cross-reference in `84-v2.5-milestones.md` is
  sufficient.
- Do **not** add stub gate entries for `SENSOR-EVAL-001` or
  `SENSOR-ROI-001` to `quality-gates.json` at v0.13.5. Stub gates
  mask the actual gap.

## Compatibility

- No code changes.
- No public API changes.
- No schema changes.

## Consequences

- The roadmap stays honest: M7 is open until the trigger criteria are
  met.
- A future cycle that produces a promoted sensor with fixture
  evaluation has a checklist (this ADR §"Trigger criteria") to act on
  without re-auditing.
- The audit-only nature of this ADR is appropriate for v0.13.5: no
  behavior changes, no risk of regression.

## Verification commands

```bash
# M7 surfaces are present
ls python/src/archskillkit/sensor_*.py
ls python/tests/test_sensor_*.py

# LEARN-NO-AUTO-ACCEPT-001 contract: explicit thresholds required
grep -A2 'min-precision\|min-recall' \
    python/src/archskillkit/delivery/cli/promote_sensor.py

# Gate catalog has no SENSOR-EVAL / SENSOR-ROI stubs (this is desired)
python3 -c "
import json
gates = json.load(open('docs/v2/verification/quality-gates.json'))['gates']
ids = [g['id'] for g in gates]
assert 'SENSOR-EVAL-001' not in ids, 'stub gate exists — revisit ADR-0052'
assert 'SENSOR-ROI-001' not in ids, 'stub gate exists — revisit ADR-0052'
print('OK: no SENSOR-EVAL/ROI stubs')
"
```
