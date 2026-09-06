# ADR-0058 — Composition Root Pattern — `ArchSkillKitApplication.for_repo(...)` as the Sole Construction Seam

Status: Proposed

## Context

The `ArchSkillKitApplication.for_repo(...)` entry point is the only sanctioned construction site for `ArchitectureWorld` and `CodeIndex`. Four delivery adapter files currently bypass this seam with direct `ArchitectureWorld.for_repo()` or `CodeIndex(` constructions (`proposals.py:169`, `simulate.py:255`, `control_plane.py:3496`, `control_plane.py:3586`), producing `ARCH-WIRING-001` violations. A `world._arch_app` reverse-handle hack lets adapters reach back into the world, creating meaning connascence. The `replay_fixture` use case requires a sandbox-managed exception: the fixture IS the world, so it must construct a transient `ArchSkillKitApplication` internally.

## Decision

`ArchSkillKitApplication.for_repo(...)` is the **ONLY** sanctioned entry point that builds `ArchitectureWorld` + `CodeIndex`. All delivery adapters MUST route through `app.<method>` facade calls. The `world._arch_app` reverse-handle hack is prohibited.

`app.replay_fixture(fixture_dir, *, write_golden=False, env=None) -> ReplayResult` is the **ONLY** sanctioned "nested composition root" pattern. It constructs a transient `ArchSkillKitApplication.for_repo(tempdir)` internally because the fixture IS the world.

The 4 unsanctioned `ARCH-WIRING-001` hits are closed by future A-full sub-cycles under ADR-0057's A-full mandate (not by this cycle's documentation-only work).

### Unsanctioned Hits (closure targets for future sub-cycles)

| File | Line | Current construction |
|------|------|---------------------|
| `proposals.py` | 169 | `ArchitectureWorld.for_repo(...)` |
| `simulate.py` | 255 | `ArchitectureWorld.for_repo(...)` |
| `control_plane.py` | 3496 | `ArchitectureWorld.for_repo(...)` |
| `control_plane.py` | 3586 | `CodeIndex(` |

All four MUST route through `app.simulate(...)`, `app.<method>` facade calls, or the `replay_fixture` sandbox exception.

### Reverse-Handle Hack (prohibited)

`world._arch_app = self` (used by `status.py:34`, `ask.py:35`, `gate.py:59`) creates meaning connascence. Adapters MUST call `app.status()`, `app.ask()`, `app.gate()` directly. The reverse handle is removed by future A-full sub-cycles.

### Six Wrappers (future A-full sub-cycle)

A future sub-cycle adds these 6 wrappers to `bootstrap/__init__.py`:

| Wrapper | Backing service | Call-site use case |
|---------|---------------|-------------------|
| `app.simulate` | `SimulationService` | replay simulation |
| `app.replay_fixture` | (transient) | fixture replay |
| `app.distill_sensors` | `SensorService` | distill sensor readings |
| `app.promote_sensor` | `SensorService` | promote sensor |
| `app.reject_sensor` | `SensorService` | reject sensor |
| `app.mine_conformance` | `ConformanceService` | mine conformance |

## Supersedes / Extends

Extends ADR-0046. Extends ADR-0047.

**Extends**: `ADR-0046-application-api-composition-root` (composition root canonical). **Closes**: `INC-M2-001` (M2 cross-CLI imports — in shape at this cycle; substance closed by future sub-cycles under ADR-0057's A-full mandate).

| # | Alternative | Why not chosen |
|---|-------------|----------------|
| 1 | **`ArchSkillKitApplication.for_repo(...)` as ONLY seam; `app.replay_fixture` as ONLY sandbox exception** (CHOSEN) | n/a |
| 2 | Keep `ArchitectureWorld.for_repo()` exposed; document "use composition root when possible" | Allows the 4 unsanctioned `ARCH-WIRING-001` hits to persist; reverses M0 closure |
| 3 | Use a registry-based composition root (`app.dispatch(command_name, **kwargs)`) | Generic dispatch lowers OCP cost but is a larger architectural change; out of scope for v2.5 |

## Consequences

Positive:
- One canonical seam is cheaper to enforce than many.
- The sandbox exception is bounded (one wrapper, one use case).
- Removing the reverse-handle hack eliminates meaning connascence.

Negative:
- Four delivery adapter files require refactoring to route through `app.<method>` calls (deferred to future A-full sub-cycles).
- The reverse-handle removal requires changes to `status.py`, `ask.py`, `gate.py` (deferred to future A-full sub-cycles).

## Trade-offs

The ADR is documentation-only in this cycle; the code changes are deferred to future sub-cycles. This is intentional — the v2.5 cycle's scope is the contract, not the implementation. The deferred cost is bounded by the 4 hits (each a one-method refactor).

## Supersedes / Extends

**Extends**: `ADR-0046-application-api-composition-root` (composition root canonical). **Extends**: `ADR-0047-delivery-adapters-are-siblings`. **Closes**: `INC-M2-001` (M2 cross-CLI imports — in shape at this cycle; substance closed by future sub-cycles under ADR-0057's A-full mandate).

## Verification

Gates touched: `ARCH-WIRING-001`, `ARCH-DELIVERY-001`.

Test files: existing `python/tests/test_bootstrap.py` (extend with wrapper integration tests in future sub-cycle); new `python/tests/test_replay_fixture_sandbox.py` (sandbox exception unit test in future sub-cycle).

Evidence command: `grep -rE 'ArchitectureWorld\.for_repo|CodeIndex\(' python/src/archskillkit/delivery/ | grep -v replay_fixture` returns 0 hits after future sub-cycles apply.

Ledger events: `cycle.apply.complete` (future sub-cycle); vault node `adrs/ADR-0058-composition-root-pattern.md` creation (this cycle, Phase E).

Source traceability: proposal.md sha256 `eb437176358e` · spec.md sha256 `c814be1d` · design.md sha256 `1d9dc45e`.

## Acceptance Criteria

1. The 4 unsanctioned `ARCH-WIRING-001` hits (`proposals.py:169`, `simulate.py:255`, `control_plane.py:3496`, `control_plane.py:3586`) are named as closure targets for future A-full sub-cycles under ADR-0057's A-full mandate.
2. The `replay_fixture` sandbox exception is documented as the **only** sanctioned "nested composition root" pattern, with signature `app.replay_fixture(fixture_dir, *, write_golden=False, env=None) -> ReplayResult`.
3. The `world._arch_app` reverse-handle hack is documented as prohibited; `status.py`, `ask.py`, `gate.py` must route through `app.status()`, `app.ask()`, `app.gate()` directly.
4. The 6 future wrappers (`app.simulate`, `app.replay_fixture`, `app.distill_sensors`, `app.promote_sensor`, `app.reject_sensor`, `app.mine_conformance`) are listed with their backing service and call-site use case.
5. `INC-M2-001` cross-CLI imports in `mcp.py` (3 hits at lines 154, 448, 451) are noted as closed in shape by this ADR; substance closed by future A-full sub-cycles.

## Reversibility

**LOW** — only composition seam documentation. Reverting re-permits the 4 unsanctioned `ARCH-WIRING-001` hits. Mechanical revert is one-file revert; semantic revert is significant.

## Deciders

rubentxu

## Date

2026-09-06

## References

- Proposal: `p-f58d41952fdf56c1/v2-5-alignment-adr/propose/proposal.md` (sha256 eb437176358e)
- Spec: `p-f58d41952fdf56c1/v2-5-alignment-adr/specify/spec.md` (sha256 c814be1d)
- Design: `p-f58d41952fdf56c1/v2-5-alignment-adr/design/design.md` (sha256 1d9dc45e)
- Explore report: `p-f58d41952fdf56c1/v2-5-alignment-adr/explore/explore-report.md` (sha256 236ae5cb0962e7b939e154c979abfa4f35a5eccd22f910fdf941c12f96a6f8c4)
