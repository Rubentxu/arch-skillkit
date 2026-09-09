# Audit Report — V2.5 Milestones M6/M7/M8 Status (Honest)

## Status

**Accepted** — Honest audit of remaining V2.5 milestones. M6 is PARTIAL,
M7 is PARTIAL, M8 is DEFERRED. No new functionality introduced.

## Context

After closing M3 (v0.14.1) and M4 (v0.14.2) as audit-only cycles, three
V2.5 milestones remain: M6 (Context), M7 (Learning), M8 (Federation).
This audit determines what is in place vs. genuinely deferred, so future
cycles can make scope decisions based on evidence rather than hope.

## Evidence

### M6 — Context & Agent Efficiency

#### SESSION-STALE-001 (PASS)

`python -m pytest python/tests/test_ask_sessions.py` → 17/17 pass.

The 10 `TestAgentSession` tests cover:
- `test_open_lease_binds_current_revisions`
- `test_stale_detection_after_world_moves`
- `test_stale_detection_after_code_generation_changes`
- `test_stale_detection_all_three_dimensions`
- `test_session_is_current_round_trip`
- `test_closed_sessions_never_go_stale`
- `test_sessions_persist_across_store_instances`
- `test_session_matches_design_schema`
- `test_session_extra_fields_forbidden`
- `test_sessions_live_outside_the_world`

Implementation: `python/src/archskillkit/application/queries/agent_session.py`
+ `python/src/archskillkit/runtime_state/agent_sessions.py`.

The `AgentSessionStore.detect_stale()` runs on every `open_agent_session()` call
and marks leases whose revisions no longer match the current snapshot.

Detection rate on fixtures: **1.0** (all stale fixtures detected as stale).

#### CTX-BUDGET-001 (PARTIAL — environment issues, not code gaps)

`python -m pytest python/tests/test_context.py python/tests/test_cli.py -k 'budget or context'`
→ 3 failed, 24 passed.

Failures:
1. `test_context_pack_via_cli` — `No module named archskillkit` (subprocess PYTHONPATH)
2. `test_context_without_world_fails_cleanly` — same PYTHONPATH issue
3. `test_subject_narrows_the_pack` — fixture drift (`endpoint@11` not in current
   Kotlin demo fixture)

These are **test environment / fixture hygiene** issues, not M6 budget
implementation gaps. The context budget enforcement itself lives in
`python/src/archskillkit/application/queries/context_query.py` and exposes
`--max-nodes`, `--max-edges`, `--max-lines` parameters.

**Action**: M6 budget gate is documented as PARTIAL. Resolving the 3 test
failures is out of scope for this audit-only cycle; they belong to a
test-environment-hygiene cycle.

### M7 — Learning Architecture

#### LEARN-NO-AUTO-ACCEPT-001 (PASS)

The `promote_sensor` CLI command requires a `--threshold` parameter
(introduced in v0.12.0). The threshold forces human review; no auto-accept
path exists in the sensor pipeline.

Implementation: `python/src/archskillkit/application/commands/sensors.py`
+ `python/src/archskillkit/sensor_candidate.py`.

#### SENSOR-EVAL-001 / SENSOR-ROI-001 (NOT IMPLEMENTED)

The roadmap declares three M7 gates (`LEARN-NO-AUTO-ACCEPT-001`,
`SENSOR-EVAL-001`, `SENSOR-ROI-001`). Only the first is registered in
`docs/v2/verification/quality-gates.json`. The other two are **missing
from the gate catalog entirely** — they have no enforcement path.

Furthermore, no code path measures LLM calls or token usage against
sensor-based shortcuts. The roadmap exit criterion "`measurable LLM
calls/tokens avoided`" requires:

1. Instrumentation of LLM invocations (counter per call site)
2. Counterfactual comparison: "what would this query have cost without the sensor?"
3. Aggregation layer that reports ROI per sensor

This is real new work — design + implementation. It cannot be closed by
audit. M7 is PARTIAL.

**Action**: M7 ROI gate is deferred until:
- A sensor with non-trivial LLM cost exists (currently sensors are
  distillation proposals, not yet deployed at scale)
- A design for instrumentation is approved (separate ADR)

### M8 — Federation Spike

**DEFERRED per backlog trigger.**

Roadmap (`docs/v2/83-v2.5-roadmap.md`):

> Sólo si existe necesidad real multi-repo.
> Gate de decisión:
> - >= 3 concrete UATs que no puedan resolverse adecuadamente repo-scoped;
> - snapshot federation sin shared mutable DB;
> - coste/valor documentado.

Backlog (`docs/v2/87-v2.5-backlog-deferred.md`):

> ## Federation decision trigger
> Sólo abrir ADR de implementación cuando existan al menos tres UATs reales
> multi-repo y una solución repo-scoped resulte insuficiente.

Current state: **0 multi-repo UATs exist**. All UAT plans (v2.1, v2.5)
validate single repos:
- `slot1-rust`: Rubentxu/software-development-decision-kernel
- `slot2-ts-saas`: calcom/cal.diy
- `slot3-kotlin`: Rubentxu/pipeline-kotlin

The trigger (`>= 3 concrete multi-repo UATs`) is unmet. M8 is deferred.

**Action**: No work required. The decision gate and trigger are documented
for future use.

## Decision

| Milestone | Status | Closure action |
|---|---|---|
| **M6** | PARTIAL | SESSION-STALE-001 closed; CTX-BUDGET-001 deferred (env issues, not code) |
| **M7** | PARTIAL | LEARN-NO-AUTO-ACCEPT-001 closed; SENSOR-ROI-001 deferred (requires design) |
| **M8** | DEFERRED | Backlog trigger unmet |

The V2.5 roadmap is **functionally complete** for the milestones with
deterministic gates (M0–M5 + M6 SESSION-STALE-001 + M7 LEARN-NO-AUTO-ACCEPT-001).
Remaining items either require test-environment work, design + new code, or
external trigger.

## Consequences

- The roadmap is **honestly documented**, not over-stated.
- M6 budget gate failures (3) are tracked as a separate hygiene cycle
  in the backlog (out of scope here).
- M7 ROI gate remains a design item in `docs/v2/87-v2.5-backlog-deferred.md`
  or a future "Next" ADR.
- M8 federation remains gated by the documented trigger.

## Verification commands

```bash
# M6 SESSION-STALE-001 evidence
python -m pytest python/tests/test_ask_sessions.py -v

# M6 CTX-BUDGET-001 evidence (note the 3 env failures)
python -m pytest python/tests/test_context.py python/tests/test_cli.py -k 'budget or context' -v

# M7 LEARN-NO-AUTO-ACCEPT-001 (CLI requires --threshold)
python -m archskillkit promote-sensor --help

# M7 ROI code absence
grep -rn 'tokens_avoided\|llm_calls_avoided' python/src/archskillkit/

# M8 trigger unmet
grep -rn 'cross.repo\|multi.repo' docs/v2/uat/
```
