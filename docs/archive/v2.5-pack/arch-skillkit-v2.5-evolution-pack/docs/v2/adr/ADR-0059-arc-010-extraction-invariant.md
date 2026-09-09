# ADR-0059 — ARC-010 — Extraction Invariant for `application/commands/`

Status: Proposed

## Context

Extracting an application use case (creating a new `python/src/archskillkit/application/commands/*.py` file) MUST NOT import `archskillkit.delivery.*`, `archskillkit.world`, `archskillkit.codeindex`, `archskillkit.activegraph`, or `archskillkit.persistence` — even under `TYPE_CHECKING`. The use case takes `ArchitectureWorldPort` (from `archskillkit.ports:17`) as a constructor argument. Type-check-only imports of the concrete classes are also forbidden because they create the connascence-of-meaning the abstract was meant to remove.

The M2 sibling draft demonstrated the failure: the "extraction introduces the violation it was meant to close" trap. Five M2-branch audit findings are the prevented failure pattern: `replay.py:47` (ARC-002), `simulation.py:49` (ARC-002), `simulation.py:16` (ARC-004), `conformance.py:16` (ARC-004), `sensors.py:22` (ARC-004).

Scope is **EXCLUSIVELY `python/src/archskillkit/application/commands/`** in v2.5. This scope is intentional — `application/queries/` (~17 files) and `application/models/` are out of scope per the orchestrator constraint.

## Decision

The following imports are **forbidden** in all `python/src/archskillkit/application/commands/*.py` files, including inside `TYPE_CHECKING` blocks:

| Forbidden prefix | Rationale |
|-----------------|-----------|
| `archskillkit.delivery` | Delivery adapters are peers, not dependencies |
| `archskillkit.world` | World is owned by the composition root |
| `archskillkit.codeindex` | Index is owned by the composition root |
| `archskillkit.activegraph` | ActiveGraph is a delivery-world concern |
| `archskillkit.persistence` | Persistence is a delivery-world concern |

The use case takes `ArchitectureWorldPort` (from `archskillkit.ports:17`) as a constructor argument. This is the only sanctioned way for an application command to interact with the world.

### M2 Audit Findings (prevented failure pattern)

These findings from the M2 sibling branch demonstrate the failure mode this ADR prevents:

| File | Line | Finding |
|------|------|---------|
| `replay.py` | 47 | ARC-002: `archskillkit.delivery` import |
| `simulation.py` | 49 | ARC-002: `archskillkit.delivery` import |
| `simulation.py` | 16 | ARC-004: `archskillkit.world` TYPE_CHECKING import |
| `conformance.py` | 16 | ARC-004: `archskillkit.world` TYPE_CHECKING import |
| `sensors.py` | 22 | ARC-004: `archskillkit.world` TYPE_CHECKING import |

## Decision Table

| # | Alternative | Why not chosen |
|---|-------------|----------------|
| 1 | **Forbid all 5 imports (including under TYPE_CHECKING) in `application/commands/` only** (CHOSEN) | n/a |
| 2 | Allow TYPE_CHECKING-only imports | Creates connascence-of-meaning; the M2 sibling draft demonstrated the failure |
| 3 | Broaden scope to `application/queries/` (~17 files; larger blast radius) | Out of scope for v2.5; per orchestrator constraint |
| 4 | Defer to a follow-up cycle | Delays the trap closure; the M2 sibling is already stuck waiting for this invariant |

## Consequences

Positive:
- Prevents the "extraction introduces the violation it was meant to close" trap.
- Makes the DIP enforcement mechanical and verifiable.
- TYPE_CHECKING ban closes the last escape hatch for meaning connascence.

Negative:
- Developers must pass `ArchitectureWorldPort` explicitly rather than importing concrete classes.
- Existing files (none currently in `commands/` that violate this) would need refactoring.

## Trade-offs

The TYPE_CHECKING ban is load-bearing. Allowing TYPE_CHECKING imports would let developers write `from archskillkit.world import ConcreteWorld` under `TYPE_CHECKING`, which creates the same meaning connascence the abstract was meant to eliminate. The cost (explicit port passing) is lower than the benefit (verifiable connascence prevention).

## Supersedes / Extends

**Extends**: `ADR-0046-application-api-composition-root`. **Closes**: the M2-branch trap (the 5 fresh ARC violations).

## Verification

Gates touched: `ARCH-BASELINE-001` (must remain 0 at HEAD; ARC-010 finds nothing in `governance.py`), `ARCH-APP-CONCRETE-001`.

Test files: `python/tests/test_arc_010_invariant.py` (AST-based scanner; created by T-V2.5-016).

Evidence command: `python3 docs/v2/verification/arch_conformance.py --root python/src/archskillkit --contracts docs/v2/verification/architecture-contracts.json --baseline docs/v2/verification/architecture-baseline.json` exits 0 with ARC-010 enforced.

Ledger events: `cycle.apply.complete`, vault node `adrs/ADR-0059-arc-010-extraction-invariant.md`, capability `cap-arc-010-injection-guard` registration.

Source traceability: proposal.md sha256 `eb437176358e` · spec.md sha256 `c814be1d` · design.md sha256 `1d9dc45e`.

## Acceptance Criteria

1. New contract `ARC-010-extraction-invariant` registered in `architecture-contracts.json` with `kind: forbidden_import_prefix`, `scope: ["python/src/archskillkit/application/commands/"]`, `forbidden: ["archskillkit.delivery", "archskillkit.world", "archskillkit.codeindex", "archskillkit.activegraph", "archskillkit.persistence"]`.
2. `arch_conformance.py --root python/src/archskillkit --contracts docs/v2/verification/architecture-contracts.json --baseline docs/v2/verification/architecture-baseline.json` exits 0 with ARC-010 enforced across `python/src/archskillkit/application/commands/*.py` (currently 1 file: `governance.py`).
3. A pre-merge `sddk capability run arc-010-injection-guard` runs `arch_conformance.py` with the contracts JSON above and fails the merge if any new `application/commands/*.py` file introduces an ARC-010 hit. (CLI divergence noted: `sddk capability register` is not in SDDK 1.79.0; the capability is documented in vault and invoked via `arch_conformance.py` directly in CI.)
4. The 5 M2-branch audit findings (`replay.py:47`, `simulation.py:49`, `simulation.py:16`, `conformance.py:16`, `sensors.py:22`) are explicitly cited as the failure pattern this ADR prevents.
5. A test `python/tests/test_arc_010_invariant.py` exists that asserts every `python/src/archskillkit/application/commands/*.py` file has NO import from any of the 5 forbidden prefixes, including under `TYPE_CHECKING` (uses `ast.parse`, not regex).

## Reversibility

**MEDIUM** — adding a new ARC rule is mechanically reversible (delete the rule from `architecture-contracts.json` and delete `test_arc_010_invariant.py`). The behavioural change is one-way: once `application/commands/*.py` files are written to comply with ARC-010, un-complying would require rewriting use cases.

## Deciders

rubentxu

## Date

2026-09-06

## References

- Proposal: `p-f58d41952fdf56c1/v2-5-alignment-adr/propose/proposal.md` (sha256 eb437176358e)
- Spec: `p-f58d41952fdf56c1/v2-5-alignment-adr/specify/spec.md` (sha256 c814be1d)
- Design: `p-f58d41952fdf56c1/v2-5-alignment-adr/design/design.md` (sha256 1d9dc45e)
- Explore report: `p-f58d41952fdf56c1/v2-5-alignment-adr/explore/explore-report.md` (sha256 236ae5cb0962e7b939e154c979abfa4f35a5eccd22f910fdf941c12f96a6f8c4)
