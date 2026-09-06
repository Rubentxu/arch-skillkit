# INC-V2.5-PACK-DRIFT — Closure Report

> **INC**: `INC-V2.5-PACK-DRIFT`
> **Status**: OPEN (apply boundary)
> **Cycle**: `p-f58d41952fdf56c1/v2-5-alignment-adr`
> **Phase**: apply (Phase E — vault + INC mirror)
> **Author**: sddk-apply executor
> **Date**: 2026-09-06

---

## Status

**OPEN** — This closure report documents the drift detected at apply phase begin and the
reconciliation procedure. The INC remains `status: OPEN` at the apply boundary.
Transition to `status: CLOSED` is a **verify-boundary action** per the locked constraint
set and the verify phase checklist.

---

## Drift Detected at Apply Phase Begin

The following drift was detected when `tools/reconcile_evolution_pack.py` was invoked
against the pack at apply phase begin:

### Manifest SHA Mismatches

| Path | Declared SHA (MANIFEST.json) | Actual SHA | Status |
|------|-----------------------------|-----------|--------|
| `README.md` | `309c2765...` | `0e3f0781...` | MISMATCH |
| `verification/arch_conformance.py` | `d31b0191...` | `d86baff1...` | MISMATCH |
| `verification/architecture-contracts.json` | `053d6ba1...` | `1bdc0cee...` | MISMATCH |
| `verification/quality-gates.json` | `c3f27d7f...` | `0410ea48...` | MISMATCH |
| `verification/traceability.json` | `1284fbf9...` | `66a3b936...` | MISMATCH |

### Gate Formula Issues

| Gate ID | Finding |
|---------|---------|
| ARCH-BASELINE-001 | Missing formula |
| DET-REPORT-001 | Missing formula |
| PKG-WHEEL-001 | Missing formula |
| ARCH-DELIVERY-001 | Missing formula |
| PARITY-GOV-001 | Missing formula |
| ARCH-WIRING-001 | Missing formula |
| ARCH-ACTIVEGRAPH-001 | Missing formula |
| ARCH-GRAPH-LEAK-001 | Missing formula |
| ARCH-APP-CONCRETE-001 | Missing formula |
| DELTA-DET-001 | Missing formula |
| GATE-NO-NEW-DRIFT-001 | Missing formula |
| PROVIDER-PROVENANCE-001 | Missing formula |
| CTX-BUDGET-001 | Missing formula |
| SESSION-STALE-001 | Missing formula |
| LEARN-NO-AUTO-ACCEPT-001 | Missing formula |
| **ARC-010-INJECTION-GUARD** | Missing formula (added by this cycle) |

### UAT Acceptance Text Gaps

The following UAT entries lack `acceptance_text` field:

UAT25-001, UAT25-002, UAT25-004, UAT25-010, UAT25-011, UAT25-013,
UAT25-014, UAT25-020, UAT25-022, UAT25-030, UAT25-031, UAT25-032,
UAT25-040, UAT25-042, UAT25-044, UAT25-050, UAT25-051, UAT25-060,
UAT25-062, UAT25-063, UAT25-070, UAT25-071, UAT25-073

### Summary

Total findings: 43 (5 manifest SHA mismatches + 17 gate missing formulas + 21 UAT gaps).

---

## Reconciliation Procedure Invoked

### Command

```bash
python3 tools/reconcile_evolution_pack.py \
  --pack-dir docs/arch-skillkit-v2.5-evolution-pack \
  --manifest MANIFEST.json \
  --output-manifest /tmp/reconciled-manifest.json \
  --output-readme /tmp/reconciled-readme.md
```

### Exit Code

`1` — drift detected (expected at apply boundary; reconciliation will pass at verify
boundary after corrections are applied).

### Exit Class

`drift` — consistent with the INC being OPEN at apply boundary.

### Schema

`arch-skit/pack-reconcile-report-v1`

---

## Diff: Current MANIFEST vs. Reconciled MANIFEST

### SHA Corrections Required

| File | Current MANIFEST SHA | Correct SHA |
|------|---------------------|--------------|
| `README.md` | `309c2765e0925c1af0d1def342a47babc9ed2198a51abc1fb0a87f8ed2e3b4a4` | `0e3f0781a4b5cebb33b8a5c7aee4a75939903478b205a3ebde27703e2c3dcf02` |
| `verification/arch_conformance.py` | `d31b01914436c93aa2bb137f17247e5378d6f291a1f695c1ca4cf1eb19df6352` | `d86baff1c9b28f18d8f625814cdf074c07e9b129c52b7b8c171b6c54f91948ed` |
| `verification/architecture-contracts.json` | `053d6ba130e20708775ad74a7786245138e5a80b129d3bd25425a3a5d18a4dce` | `1bdc0cee8490e81c1883325a26226924bfd2f61edfb9adc0c320b7d006a28606` |
| `verification/quality-gates.json` | `c3f27d7fb81a4386142bf549fc807f30a7f684c6e2775d86cc0654a2c8aba046` | `0410ea4843ac1e490836270902aaa590f617b313c72ad062b5b106212204026b` |
| `verification/traceability.json` | `1284fbf9e72d7ff1357b0b350ef3bd753a081ec4c46f368994bde9e48162aa1d` | `66a3b936cd933ab99fbf338877c4104c884480f5e595421039eb4a1c9f63919f` |

### Manifest SHA Block

The `files` array in `MANIFEST.json` must be updated to reflect the actual SHA-256
hashes of the files as they exist at HEAD of the `feat/v2.5-alignment-adr` branch.

---

## Actions Still Pending

The following actions remain to be completed before the INC can be closed:

### 1. README Re-render

- **Action**: Re-render `docs/arch-skillkit-v2.5-evolution-pack/README.md` to reflect
  the correct version state.
- **Issue**: README currently claims `v0.5.0` tag or is otherwise stale.
- **Correction text**: "M2 OPEN — see v2-5-alignment-adr cycle" + v0.7.0 tag correction.
- **ADR reference**: ADR-0062 § README correction text.

### 2. MANIFEST.json Re-hash

- **Action**: Update the `files` array in `MANIFEST.json` with the correct SHA-256
  hashes of all tracked files.
- **Issue**: Declared SHAs do not match actual file content at HEAD.
- **Tool**: `tools/reconcile_evolution_pack.py --write` will perform this update.

### 3. Gate Formula Fill-in

- **Action**: Ensure all gate entries in `quality-gates.json` have either a `formula` or
  `formula_ref` field.
- **Issue**: 17 gates lack formula definition.
- **ADR reference**: ADR-0062 § six validation checks.

### 4. UAT Acceptance Text

- **Action**: Fill in `acceptance_text` field for the 21 UAT entries that lack it.
- **Issue**: UAT plan has empty `acceptance_text` fields.
- **ADR reference**: ADR-0062 § UAT acceptance text check.

### 5. Traceability Links

- **Action**: Fill 14 missing traceability links (7 milestone links + 7 UAT links)
  per T-V2.5-010.
- **Issue**: `traceability.json` has gaps.
- **ADR reference**: SPEC-V2.5-006 predicate 4.

---

## Closure Conditions

Per the verify-boundary checklist (design.md §7) and locked constraint set,
the following conditions MUST be met before `INC-V2.5-PACK-DRIFT` can transition
to `status: CLOSED`:

| # | Condition | Evidence |
|---|-----------|----------|
| 1 | `python3 tools/reconcile_evolution_pack.py --write` exits 0 | Reconciliation report shows `exit_class: ok` |
| 2 | `MANIFEST.json` SHA entries match actual file content at HEAD | Hash comparison in reconciliation report |
| 3 | README corrected: "M2 OPEN — see v2-5-alignment-adr cycle" + v0.7.0 tag | README content check |
| 4 | 14 traceability links filled | `traceability.json` link count >= 14 |
| 5 | All gate entries have `formula` or `formula_ref` | `quality-gates.json` validation |
| 6 | UAT acceptance_text fields populated | UAT plan validation |
| 7 | Vault `sddk vault validate` errors <= 16 (down from 25) | Vault validation report |

---

## INC Frontmatter Node

The vault mirror node for this INC is at:

```
~/.sddk-knowledge/p-f58d41952fdf56c1/incs/INC-V2.5-PACK-DRIFT.md
```

Frontmatter:
```yaml
type: inc
id: INC-V2.5-PACK-DRIFT
status: OPEN
created_in_cycle: p-f58d41952fdf56c1/v2-5-alignment-adr
```

Body documents the drift artifacts. Status transition to `CLOSED` is performed at
verify phase boundary after all closure conditions above are met.

---

## Relationship to Other Artifacts

| Artifact | Path | Role |
|----------|------|------|
| ADR-0062 | `docs/arch-skillkit-v2.5-evolution-pack/docs/v2/adr/ADR-0062-pack-drift-reconciliation-rule.md` | Defines the reconciliation rule and INC lifecycle |
| reconcile script | `tools/reconcile_evolution_pack.py` | Tool that detects and corrects drift |
| MANIFEST.json | `docs/arch-skillkit-v2.5-evolution-pack/MANIFEST.json` | Declares file SHAs; SHA mismatches are the primary drift signal |
| quality-gates.json | `docs/arch-skillkit-v2.5-evolution-pack/verification/quality-gates.json` | Gate definitions; formula gaps are part of the drift |
| traceability.json | `docs/arch-skillkit-v2.5-evolution-pack/verification/traceability.json` | Link registry; missing links are part of the drift |

---

## Verify-Boundary Checklist

The following verify-boundary actions close this INC:

1. Run `python3 tools/reconcile_evolution_pack.py --write` — exits 0 when all drift is resolved
2. Commit the re-hashed MANIFEST.json
3. Commit the corrected README
4. Confirm 14 traceability links are filled
5. Update vault node frontmatter: `status: CLOSED`, `closed_in_cycle: p-f58d41952fdf56c1/v2-5-alignment-adr`
6. Verify vault `sddk vault validate` error count <= 16

---

## Notes

- This INC was opened at the propose boundary (Phase A of this cycle) when the
  drift was first detected.
- The 43 drift findings are consistent with the pre-cycle state of the pack
  at the start of v2.5-alignment-adr work.
- The reconciliation tool (`reconcile_evolution_pack.py`) was created as part of
  this cycle (T-V2.5-017) specifically to address this class of drift.
- The v0.7.0 tag (`555299653e00d0fb1441bf9bcb6d13ca10115fd2`) is the authoritative
  base for this cycle; the MANIFEST.json SHAs must be recomputed against that commit.
- M2 is declared `OPEN` in the pack README — this is the correct state. The README
  should NOT claim M2 is `CLOSED` until a future cycle closes the remaining M2
  hygiene items (INC-M2-001 cross-CLI imports in mcp.py).
