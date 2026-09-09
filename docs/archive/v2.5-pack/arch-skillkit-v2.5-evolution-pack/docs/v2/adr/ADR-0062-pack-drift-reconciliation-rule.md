# ADR-0062 — Pack Drift Reconciliation Rule

Status: Proposed

## Context

The v2.5 evolution pack's `MANIFEST.json` declares a README sha of `309c2765...` but the live file sha is `0e3f0781...` (4732 bytes). The pack README also claims v0.5.0 as the current version while HEAD is v0.7.0. Seven milestone links and seven UAT links are missing from `traceability.json`. The `APP-COVERAGE-001` gate lacks a formal `formula` field. The pack self-consistency is not machine-verified.

The v2.5 alignment cycle addresses this by adding a reconciliation script and a formal INC (`INC-V2.5-PACK-DRIFT`) to track the closure of these gaps.

## Decision

### Pack Reconciliation Script

A `pack validate` script at `tools/reconcile_evolution_pack.py` (NOT inside the pack; per orchestrator constraint) asserts:

1. **MANIFEST sha**: Every file listed in `MANIFEST.json` matches the sha recorded in the manifest.
2. **Gate formula**: Every gate in `quality-gates.json` has a `formula` field or a `formula_ref` field.
3. **UAT acceptance text**: Every UAT in `uat-v2.5-plan.json` has a non-empty `acceptance_text` field.
4. **Traceability link consistency**: Every link in `traceability.json` references an ADR that exists in `adr/`, a gate that exists in `quality-gates.json`, and a UAT that exists in `uat-v2.5-plan.json`.

### CLI Interface

```bash
tools/reconcile_evolution_pack.py \
  --pack-dir docs/arch-skillkit-v2.5-evolution-pack \
  --manifest MANIFEST.json \
  --output-manifest MANIFEST.json.reconciled \
  --output-readme README.reconciled.md
```

**Exit codes**:
- `0` (exit 0): Pack is fully reconciled (all checks pass).
- `1` (exit 1): Validation error (missing formula, missing acceptance_text, malformed structure).
- `2` (exit 2): Drift detected (sha mismatch, missing link targets).

### README Correction

Until the alignment ADR verifies, the pack README's M2 status row is corrected to: `M2 OPEN — see v2-5-alignment-adr cycle`. The v0.5.0 tag claim is corrected to v0.7.0.

### INC-V2.5-PACK-DRIFT Closure Procedure

`INC-V2.5-PACK-DRIFT` is opened at the propose phase. It is closed at the verify phase via:

1. Run `tools/reconcile_evolution_pack.py --pack-dir docs/arch-skillkit-v2.5-evolution-pack --manifest MANIFEST.json --output-manifest ... --output-readme ...`
2. If exit 0: write closure report to `verification/INC-V2.5-PACK-DRIFT-close.md`.
3. Set vault node `incs/INC-V2.5-PACK-DRIFT.md` status to CLOSED.

## Decision Table

| # | Alternative | Why not chosen |
|---|-------------|----------------|
| 1 | **Reconciliation script at `tools/reconcile_evolution_pack.py`; verify phase closes INC-V2.5-PACK-DRIFT after MANIFEST re-hash** (CHOSEN) | n/a (orchestrator-locked) |
| 2 | Script under `docs/arch-skillkit-v2.5-evolution-pack/scripts/` | The pack is a deliverable; tools are buildable. Keeping reconcile under `tools/` puts it with the other buildable scripts |
| 3 | No script; hand-maintain pack self-consistency | Status quo; the drift is the proof this fails |

## Consequences

Positive:
- Pack self-consistency is machine-verified.
- The 14 missing links are filled or waived.
- MANIFEST sha mismatch is resolved.
- The INC provides a tracking mechanism for pack hygiene.

Negative:
- The reconciliation script adds a dependency on Python tooling outside the pack.
- Exit code 2 (drift) is advisory in `mise run verify:pack` but could be made CI-mandatory in future cycles.

## Trade-offs

Hand-maintaining pack consistency has already been shown to fail (the drift exists). Automating the check is the only reliable path. The script is placed outside the pack to keep the pack a pure deliverable, with the reconciliation tooling in the repository's `tools/` directory.

## Supersedes / Extends

**Extends**: the pack's `MANIFEST.json` schema. **Closes**: `INC-V2.5-PACK-DRIFT` (opened at propose, closed at verify after re-render).

## Verification

Gates touched: `ARCH-BASELINE-001` (no new findings; pack self-consistency), `DET-REPORT-001` (deterministic verification).

Test files: `python/tests/test_pack_validate.py` or `tools/test_reconcile_evolution_pack.py`.

Evidence: `python3 tools/reconcile_evolution_pack.py --pack-dir docs/arch-skillkit-v2.5-evolution-pack --manifest MANIFEST.json --output-manifest /tmp/MANIFEST.json --output-readme /tmp/README.md && echo "exit 0"` runs cleanly.

Source traceability: proposal.md sha256 `eb437176358e` · spec.md sha256 `c814be1d` · design.md sha256 `1d9dc45e`.

## Acceptance Criteria

1. A `pack validate` script exists at `tools/reconcile_evolution_pack.py` that (a) reads `MANIFEST.json`, (b) computes sha256 of every file, (c) asserts match, (d) asserts each gate in `quality-gates.json` has a `formula` (or `formula_ref`), (e) asserts each UAT in `uat-v2.5-plan.json` has non-empty `acceptance_text`, (f) asserts each `traceability.json` link is internally consistent.
2. `mise.toml[tasks."verify:pack"]` invokes the script; `pack validate` exits 0 for a reconciled pack.
3. The README sha mismatch is fixed (either README updated to match MANIFEST, or MANIFEST updated to match README) and recorded in this ADR.
4. The traceability gaps (7 missing milestone links, 7 missing UAT links) are filled OR an explicit waiver is recorded in this ADR.
5. The "M2 ✓ COMPLETO" row in README is downgraded to "M2 OPEN — see v2-5-alignment-adr cycle" until the alignment ADR verifies; the v0.5.0 tag claim is corrected to v0.7.0.

## Reversibility

**MEDIUM** — pack validate script is additive; can be removed without code impact; the durable change is the habit of pack validation.

## Deciders

rubentxu

## Date

2026-09-06

## References

- Proposal: `p-f58d41952fdf56c1/v2-5-alignment-adr/propose/proposal.md` (sha256 eb437176358e)
- Spec: `p-f58d41952fdf56c1/v2-5-alignment-adr/specify/spec.md` (sha256 c814be1d)
- Design: `p-f58d41952fdf56c1/v2-5-alignment-adr/design/design.md` (sha256 1d9dc45e)
- Explore report: `p-f58d41952fdf56c1/v2-5-alignment-adr/explore/explore-report.md` (sha256 236ae5cb0962e7b939e154c979abfa4f35a5eccd22f910fdf941c12f96a6f8c4)
