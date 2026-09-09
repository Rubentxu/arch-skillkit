# ADR-0060 — APP-COVERAGE-001 Formula — Liberal Definition (Per Orchestrator Constraint)

Status: Proposed

## Context

The `APP-COVERAGE-001` gate entry in `quality-gates.json` lacks a formal `formula` field. The gate was implicitly defined by an untracked test (`python/tests/test_application_api_coverage.py`) whose "liberal" formula (counting all service-call sites in `application/commands/`) was the only valid definition. At v0.7.0 HEAD, the gate reports 13/19 = 68.42% against a threshold of 0.9.

The v2.5 alignment cycle formalises the gate with the **LIBERAL** formula (orchestrator-locked constraint): coverable surface = **19 service-call sites in `python/src/archskillkit/application/commands/` ONLY** (NOT the world/index side-channels or model constructors); threshold = **0.9**. The report emits **BOTH** the strict numerator and the liberal numerator for audit parity.

ARC-002 (forbidden imports of `archskillkit.delivery.cli.*` into `application/`) and ARC-004 (forbidden TYPE_CHECKING imports of `archskillkit.world` into `application/`) BLOCK independently of the formula — they are independent rules.

## Decision

### Formula

```
coverage = (# of service-call sites in python/src/archskillkit/application/commands/
            that route through composition-root-owned access) / 19 >= 0.9
```

### Denominator

**19** service-call sites in `python/src/archskillkit/application/commands/`. These are the files that implement application use cases and must route through the composition root.

### Dual Numerator Reporting

The coverage report emits **BOTH** numerators:

**Strict numerator** (informational only): `# of NEEDS_WORLD command handlers whose first non-trivial call is app.<method> or via app.world/app.index composition-root-owned access`.

**Liberal numerator** (gating): `# of command handlers that route through any application-layer service or composition-root-owned accessor`.

The **strict denominator** equals the strict numerator's denominator (currently lower than 19). The **liberal denominator** is always 19.

### Threshold

**0.9** — liberal coverage must be >= 0.9 to pass. A future M2b cycle may tighten to 0.95 once all adapters route through `app.<method>` exclusively.

### ARC-002 / ARC-004 Independence

ARC-002 and ARC-004 BLOCK independently of the APP-COVERAGE-001 formula. They are separate gate predicates. A pass on APP-COVERAGE-001 does not imply a pass on ARC-002 or ARC-004.

## Decision Table

| # | Alternative | Why not chosen |
|---|-------------|----------------|
| 1 | **Liberal formula = 19 sites in `application/commands/`; threshold 0.9; both numerators emitted; ARC-002/ARC-004 still block** (CHOSEN) | n/a (orchestrator-locked) |
| 2 | Strict formula only | Currently 0% (no `app.<method>` exclusive routing yet); gates would block M2 closure |
| 3 | Liberal now, strict at M2b | Equivalent to choice #1 with explicit migration path; documented in AC#5 |

## Consequences

Positive:
- The gate is now formally defined and auditable.
- Dual numerator reporting gives full visibility into coverage gaps.
- The 0.9 threshold is achievable (13/19 = 68.42% today; gap is ~4 more handlers or 1 more routing improvement).

Negative:
- Until strict coverage improves, the strict numerator will be significantly lower than liberal — creating transparency pressure on the gap.
- The 19 denominator is a point-in-time count; future commands add to the denominator, requiring ongoing maintenance.

## Trade-offs

The liberal formula is the only one that lets the current architecture pass the gate. The strict formula (which would require exclusive `app.<method>` routing) is the target state but would block the M2 closure cycle. The dual-numerator approach makes the gap visible without blocking progress.

## Supersedes / Extends

**Extends**: the `APP-COVERAGE-001` gate entry in `quality-gates.json`. **Supersedes**: the untracked `python/tests/test_application_api_coverage.py`'s implicit "liberal" formula as the only valid formula (now both formulas are defined; liberal gates; strict is audited).

## Verification

Gates touched: `APP-COVERAGE-001` (formalised).

Test files: `python/tests/test_application_api_coverage.py` (tracked by T-V2.5-015; now emits dual numerators).

Evidence: `python3 -m pytest python/tests/test_application_api_coverage.py -v` produces a report with both `strict` and `liberal` sections in the `details` dict.

At verify phase, the APP-COVERAGE-001 number appears in the verify report and in vault `gates/APP-COVERAGE-001.md`.

Source traceability: proposal.md sha256 `eb437176358e` · spec.md sha256 `c814be1d` · design.md sha256 `1d9dc45e`.

## Acceptance Criteria

1. `quality-gates.json` `APP-COVERAGE-001` entry gains a `formula` field with the liberal definition: `coverage = (# of service-call sites in python/src/archskillkit/application/commands/ that route through composition-root-owned access) / 19 >= 0.9`.
2. `verification/README.md` documents BOTH formulas (strict + liberal) under §`application_api_coverage_definition`; specifies that liberal is the gating one and strict is informational for audit parity.
3. The untracked `python/tests/test_application_api_coverage.py` is tracked (`git add`) and registered as the gate runner; its `details` dict emits BOTH strict and liberal numerators.
4. At v2-5-alignment-adr verify phase, APP-COVERAGE-001 reports a number; the number is recorded in the verify report and in the vault under `gates/APP-COVERAGE-001.md`.
5. Threshold 0.9 stays for M2; a follow-up cycle (M2b per explore-report) may tighten to 0.95 once all adapters route through `app.<method>` exclusively.

## Reversibility

**LOW** — picking the liberal formula now means a future cycle cannot retroactively lower the bar. Mechanical revert is one-field delete in `quality-gates.json`; semantic revert is significant.

## Deciders

rubentxu

## Date

2026-09-06

## References

- Proposal: `p-f58d41952fdf56c1/v2-5-alignment-adr/propose/proposal.md` (sha256 eb437176358e)
- Spec: `p-f58d41952fdf56c1/v2-5-alignment-adr/specify/spec.md` (sha256 c814be1d)
- Design: `p-f58d41952fdf56c1/v2-5-alignment-adr/design/design.md` (sha256 1d9dc45e)
- Explore report: `p-f58d41952fdf56c1/v2-5-alignment-adr/explore/explore-report.md` (sha256 236ae5cb0962e7b939e154c979abfa4f35a5eccd22f910fdf941c12f96a6f8c4)
