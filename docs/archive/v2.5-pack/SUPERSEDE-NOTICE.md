# V2.5 Evolution Pack — Superseded

> **Status**: ARCHIVED (preserved for audit trail)
> **Superseded by**: PR #3 (v0.11.0), released 2026-09-09
> **Closes**: Issue #1

## Why archived

This pack was the seed implementation of the architecture conformance verifier
during the v2.5 alignment-ADR cycle. It was imported from the upstream evolution
pack during v0.4.0 and lived under `docs/arch-skillkit-v2.5-evolution-pack/`
(an unversioned import directory).

In v0.11.0 the verifier was ported to the canonical location
`docs/v2/verification/arch_conformance.py` with three material improvements:

1. **ARC-010** (ArchitectureWorld sandbox, ADR-0049) — direct construction of
   `ArchitectureWorld.for_repo` or `CodeIndex(` outside the sandbox is forbidden.
   Detects 17 current violations.
2. **APP-COVERAGE-001** (CLI routes via application layer) — dual numerator
   with ARC-010. Current coverage **0.6842** (13/19 CLI files route through
   app). Reported as a non-blocking metric until M3 closes the gap.
3. **Path resolution bug fix** — dual layout support
   (`--root=python/src/archskillkit` and `--root=.` with fallback).

## What changed in v0.11.0

- `docs/v2/verification/arch_conformance.py` (canonical verifier)
- `docs/v2/verification/architecture-contracts.json` (scoped to actual repo paths)
- `docs/v2/verification/architecture-baseline.json` (22 known findings)

## What's preserved here

The full pack contents are preserved under
`docs/archive/v2.5-pack/arch-skillkit-v2.5-evolution-pack/` for these reasons:

- **Audit trail**: documents the v2.5 cycle that was authored off-trunk and
  promoted through `p-f58d41952fdf56c1/v2-5-alignment-adr`.
- **Procedural evidence**: `verification/M2-SUPERSEDE-PROCEDURE.md` records the
  supersession of the orphan M2 sibling cycle; `verification/INC-V2.5-PACK-DRIFT-close.md`
  documents the drift between the declared MANIFEST.json and the actual files.
- **ADR history**: the original 17 ADRs (0046–0062) authored for v2.5. Note
  that ADRs **already live in their canonical location** under `docs/v2/adr/`
  and were reconciled there as part of v0.10.0 (commit `a0c6f71`).

## What was *not* preserved

- The unversioned import directory `docs/arch-skillkit-v2.5-evolution-pack/`
  itself is gone. This directory was never under version control's authority —
  it was an external drop that was being consumed as input, not authored.
- The pack's `arch_conformance.py` is **not** the live verifier. Running the
  pack's copy would produce stale results (no ARC-010, no APP-COVERAGE-001,
  phantom `adapters/inbound/*` paths that don't exist).

## Migration recipe (for future archives)

If you ever need to archive another evolution pack, the procedure is:

1. `git mv docs/<pack-name> docs/archive/<short-name>/`
2. Create `docs/archive/<short-name>/SUPERSEDE-NOTICE.md` with:
   - PR / commit that supersedes it
   - What was ported forward
   - Why preserved
3. Repoint any `mise.toml` or `.github/workflows/*.yml` references to the
   canonical location.
4. Validate by running the live verifier against the repo.

## Refs

- PR #3: https://github.com/Rubentxu/arch-skillkit/pull/3
- Issue #1: https://github.com/Rubentxu/arch-skillkit/issues/1
- Release v0.11.0: https://github.com/Rubentxu/arch-skillkit/releases/tag/v0.11.0
- ADR-0062 (pack-drift reconciliation rule) — the rule that triggered this archive
