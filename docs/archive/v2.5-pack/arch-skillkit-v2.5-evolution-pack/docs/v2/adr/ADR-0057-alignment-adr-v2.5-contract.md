# ADR-0057 — v2.5 Alignment Contract — Single Source of Truth for the Composition-Root Boundary

Status: Proposed

## Context

The v2.5 evolution pack (`docs/arch-skillkit-v2.5-evolution-pack/`) is a mergeable hardening of the v0.7.0 line. It commits to five load-bearing promises — (1) the Composition Root as the only sanctioned `ArchitectureWorld`/`CodeIndex` construction seam, (2) the Application API as the only semantic seam, (3) governance routing through `GovernanceApplicationService`, (4) the sandbox replay exception for fixtures, and (5) the lazy MCP import (ADDED-7) — yet the M2 milestone is declared `✓ COMPLETO` in the pack README while the gates that should prove it (`ARCH-WIRING-001`, `APP-COVERAGE-001`) fail at v0.7.0 HEAD with 4 unsanctioned hits and 68.42% coverage (threshold 0.9). A previous A-lite sibling cycle (`m2-composition-root-delivery-closure`) attempted this surface and got stuck at phase=build, leaving 5 fresh ARC violations on its branch.

## Decision

The five promises are locked as individually-gateable numbered sub-sections, each tied to an existing gate id, and any future cycle touching the composition-root seam MUST be declared `path: A-full` unless an explicit waiver sub-section with a sunset date is appended to this ADR.

### Promise 1 — Composition Root (ARCH-WIRING-001)

Only `ArchSkillKitApplication.for_repo(...)` may construct `ArchitectureWorld` or `CodeIndex`. All delivery adapters route through `app.<method>` calls. The 4 unsanctioned `ARCH-WIRING-001` hits (`proposals.py:169`, `simulate.py:255`, `control_plane.py:3496`, `control_plane.py:3586`) are closed by future A-full sub-cycles under this ADR's mandate.

Gate: `ARCH-WIRING-001`.

### Promise 2 — Application API Seam (ARCH-DELIVERY-001)

The `archskillkit.application` package is the only semantic seam for application-level use cases. No delivery adapter may import from `archskillkit.delivery.*` into `archskillkit.application.*`.

Gate: `ARCH-DELIVERY-001`.

### Promise 3 — Governance Routing (APP-COVERAGE-001)

All governance commands route through `GovernanceApplicationService`. The APP-COVERAGE-001 gate uses the LIBERAL formula (19 service-call sites in `python/src/archskillkit/application/commands/`; threshold 0.9; both strict and liberal numerators emitted for audit parity).

Gate: `APP-COVERAGE-001`.

### Promise 4 — Sandbox Exception (ARC-002/004/005)

`app.replay_fixture(fixture_dir, *, write_golden=False, env=None) -> ReplayResult` is the only sanctioned "nested composition root" pattern. It constructs a transient `ArchSkillKitApplication.for_repo(tempdir)` internally because the fixture IS the world. No other code may bypass the composition root seam.

Gates: `ARC-002`, `ARC-004`, `ARC-005`.

### Promise 5 — Lazy MCP Import (ARCH-ACTIVEGRAPH-001) — IMPLEMENTED

`delivery/cli/mcp.py` implements a lazy import guard: the four `mcp.*` imports
(`mcp.server.Server`, `mcp.server.stdio.stdio_server`, `mcp.shared.exceptions.McpError`,
`mcp.types.{ErrorData, TextContent, Tool}`) are moved from module-load scope into the
functions that need them. `handle()` (the entry point invoked when the user runs
`archskillkit mcp`) calls `_require_mcp()` which imports the four modules under a single
`try/except ImportError` and raises `RuntimeError("Install archskillkit[mcp] to use
the MCP server")` if any are missing. `build_server()` then lazy-imports `Server`;
`_tool()` and `_envelope()` each lazy-import `Tool` / `TextContent`; the McpError /
ErrorData pair is centralised in a `_raise_mcp_error()` helper used by both the
proposal envelope path and the admin gate path. This prevents `archskillkit` without
the `[mcp]` extra from failing on import — confirmed by re-importing
`archskillkit.delivery.cli.mcp` in an env without `mcp` installed (succeeds), then
calling `handle(args)` (raises the friendly RuntimeError). Click is not a runtime
dependency on this project, so a stdlib `RuntimeError` is used rather than the
``ClickException`` named in earlier drafts.

Gate: `ARCH-ACTIVEGRAPH-001`.

## Cycle Path Policy

Any cycle that modifies `ArchSkillKitApplication` lifecycle, `bootstrap/__init__.py` wrappers, the `application/commands/` boundary, the `delivery/ → application/` seam, or any `ARC-002/003/004/005/008/009/010` contract MUST be declared `path: A-full`.

Exception: A cycle may carry an explicit waiver sub-section appended to this ADR with a sunset date. The waiver must name the specific boundary touch, the risk accepted, and the date after which the waiver expires.

## M2 Supersession Notice

The orphan M2 sibling cycle (`p-f58d41952fdf56c1/m2-composition-root-delivery-closure`, status=OPEN/build) is **superseded in shape** by this cycle. Its substance is recoverable as three future A-full sub-cycles:

1. **Sub-cycle 1**: Close 4 unsanctioned `ARCH-WIRING-001` hits via `app.<method>` routing.
2. **Sub-cycle 2**: Remove `world._arch_app` reverse-handle hack; route `status.py`, `ask.py`, `gate.py` through `app.status()`, `app.ask()`, `app.gate()`.
3. **Sub-cycle 3**: Add 6 wrappers to `bootstrap/__init__.py` (`app.simulate`, `app.replay_fixture`, `app.distill_sensors`, `app.promote_sensor`, `app.reject_sensor`, `app.mine_conformance`).

This ADR does **NOT** call `sddk cycle supersede`. The orchestrator dispatches that at the verify phase boundary (recommended: at v2-5-alignment-adr verify phase).

## MANIFEST.json Reconciliation

Pack README sha MUST match `MANIFEST.json` before `phase.archive.complete` for any cycle touching this ADR. The reconciliation is performed by `tools/reconcile_evolution_pack.py` (ADR-0062). Drift is tracked as `INC-V2.5-PACK-DRIFT`.

## Decision Table

| # | Alternative | Why not chosen |
|---|-------------|----------------|
| 1 | **Lock the 5 promises as a Cycle Path Policy that mandates A-full on the boundary** (CHOSEN) | n/a |
| 2 | Lock promises as advisory (no A-full mandate) | The M2 sibling failure proves advisory does not work — orphan cycles can quietly violate ARC rules |
| 3 | Keep the boundary ungoverned; per-cycle ADRs only | Status quo; the M2 sibling shows this produces 5 fresh ARC violations per cycle attempt |

## Consequences

Positive:
- The composition-root seam is governed by a single, explicit policy.
- Future cycles cannot accidentally bypass the seam with an A-lite cycle.
- The M2 sibling's substance is recoverable as structured sub-cycles.

Negative:
- Any legitimate emergency change requires a waiver sub-section or a full A-full cycle.
- The waiver mechanism adds a documentation burden for edge cases.

## Trade-offs

The A-full mandate adds process overhead for small changes. The benefit (preventing the M2 failure pattern) outweighs this cost for changes to the highest-connascence boundary in the system.

## Supersedes / Extends

**Extends**: `ADR-0046-application-api-composition-root` (composition root canonical) + `ADR-0047-delivery-adapters-are-siblings` (sibling-adapter contract). **Supersedes**: nothing. **Closes**: `INC-M2-001` (cross-CLI imports in `mcp.py`) only in shape; the live close happens at verify phase.

## Verification

Gates touched: `ARCH-BASELINE-001`, `ARCH-DELIVERY-001`, `ARCH-WIRING-001`, `APP-COVERAGE-001`.

Test files: `python/tests/test_application_api_coverage.py` (tracked by T-V2.5-015), `python/tests/test_arc_010_invariant.py` (new; created by T-V2.5-016).

Ledger events: `cycle.specify.complete` (propose close), `cycle.archive.complete` (after MANIFEST reconcile), vault node creation `adrs/ADR-0057-alignment-adr-v2.5-contract.md`.

Source traceability: proposal.md sha256 `eb437176358e` · spec.md sha256 `c814be1d` · design.md sha256 `1d9dc45e`.

## Acceptance Criteria

1. The 5 promises appear as numbered, individually-gateable sub-sections, each tied to an existing gate id (`ARCH-DELIVERY-001`, `ARCH-WIRING-001`, `APP-COVERAGE-001`, `ARC-002/004/005`, `ARCH-ACTIVEGRAPH-001`).
2. A "Cycle Path Policy" sub-section explicitly forbids A-min and A-lite on this boundary; requires A-full or a waiver sub-section with a sunset date.
3. A "M2 Supersession Notice" sub-section records: "the orphan M2 sibling cycle (`m2-composition-root-delivery-closure`, status=OPEN/build) is superseded in shape; substance recoverable as the three future A-full sub-cycles; this ADR does NOT call `sddk cycle supersede` — the orchestrator decides when (recommended: at v2-5-alignment-adr verify phase)."
4. References `MANIFEST.json` reconciliation rule: pack README sha must match `MANIFEST.json` before `phase.archive.complete`.
5. At apply phase, the 25 non-blocking vault wikilink errors reduce by ≥9 (the 9 forward-references become live `[[wikilinks]]` once the 6 ADRs + INC node + capability are mirrored at apply).

## Reversibility

**LOW** — the alignment ADR locks the boundary contract. Reverting re-opens the composition-root seam as a free-for-all. Mechanical revert is one-file delete; semantic revert is significant.

## Deciders

rubentxu

## Date

2026-09-06

## References

- Proposal: `p-f58d41952fdf56c1/v2-5-alignment-adr/propose/proposal.md` (sha256 eb437176358e)
- Spec: `p-f58d41952fdf56c1/v2-5-alignment-adr/specify/spec.md` (sha256 c814be1d)
- Design: `p-f58d41952fdf56c1/v2-5-alignment-adr/design/design.md` (sha256 1d9dc45e)
- Explore report: `p-f58d41952fdf56c1/v2-5-alignment-adr/explore/explore-report.md` (sha256 236ae5cb0962e7b939e154c979abfa4f35a5eccd22f910fdf941c12f96a6f8c4)
