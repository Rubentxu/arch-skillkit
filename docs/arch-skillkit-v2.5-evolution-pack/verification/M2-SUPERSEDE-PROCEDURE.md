# M2 Supersede Procedure

> **Cycle**: `p-f58d41952fdf56c1/v2-5-alignment-adr`
> **Phase**: verify-boundary (NOT apply — deferred per locked constraint set)
> **Subject**: Superseding the orphan M2 sibling cycle `p-f58d41952fdf56c1/m2-composition-root-delivery-closure`

---

## Background

The M2 sibling cycle (`p-f58d41952fdf56c1/m2-composition-root-delivery-closure`) was
attempted as an A-lite cycle targeting the composition-root boundary. It reached
`status=OPEN/phase=build` and stalled, leaving 5 fresh ARC violations on its branch.
The cycle was never closed and remains in `OPEN/build` state.

The v2-5-alignment-adr cycle (this cycle) addresses the same composition-root boundary
but uses an A-full path and produces a different, more complete set of artifacts.
ADR-0057 § "M2 Supersession Notice" records that M2 is superseded in shape by this
cycle. The substance is recoverable as three future A-full sub-cycles.

---

## Supersede Invocation

The following command will be executed at the verify-phase boundary:

```bash
sddk cycle supersede \
  --successor p-f58d41952fdf56c1/v2-5-alignment-adr \
  --reason "goal-replaced" \
  --cycle p-f58d41952fdf56c1/m2-composition-root-delivery-closure
```

### Exact Rationale

- `--successor p-f58d41952fdf56c1/v2-5-alignment-adr`: This cycle (v2-5-alignment-adr)
  is the goal-replacing cycle that supersedes M2's scope.
- `--reason goal-replaced`: Per ADR-0057 § M2 Supersession Notice and locked constraint #7.
- `--cycle p-f58d41952fdf56c1/m2-composition-root-delivery-closure`: The M2 orphan
  cycle being superseded.

### Precondition Checklist

Before executing `sddk cycle supersede`, the following must hold:

| # | Precondition | Verification |
|---|-------------|--------------|
| 1 | `p-f58d41952fdf56c1/v2-5-alignment-adr` is `status=OPEN` | `sddk cycle status` shows OPEN |
| 2 | `p-f58d41952fdf56c1/v2-5-alignment-adr` has passed verify phase | `sddk ledger` shows `cycle.verify.complete` event |
| 3 | `p-f58d41952fdf56c1/m2-composition-root-delivery-closure` is `status=OPEN` | `sddk cycle status` shows OPEN |
| 4 | No unmerged work on M2 branch that must be preserved | `git log m2-branch --oneline` review |
| 5 | ADR-0057 (alignment contract) is accepted | ADR frontmatter `status: accepted` |
| 6 | Three future sub-cycle proposals are documented in ADR-0057 § "M2 Supersession Notice" | ADR-0057 content check |

### Post-Supersede State

After `sddk cycle supersede` completes:

- M2 cycle transitions to `status: superseded`
- M2 branch can be abandoned or archived
- Future work on composition-root boundary uses the three sub-cycle mandates in ADR-0057

---

## Evidence References

| Artifact | Path | Relevance |
|----------|------|-----------|
| ADR-0057 | `docs/arch-skillkit-v2.5-evolution-pack/docs/v2/adr/ADR-0057-alignment-adr-v2.5-contract.md` | Contains M2 Supersession Notice |
| ADR-0058 | `docs/arch-skillkit-v2.5-evolution-pack/docs/v2/adr/ADR-0058-composition-root-pattern.md` | Documents the construction seam that M2 attempted |
| M2 cycle artifacts | `cycle-artifacts/p-f58d41952fdf56c1/m2-composition-root-delivery-closure/` | Original M2 attempt; superseded |
| INC-M2-001 | `~/.sddk-knowledge/p-f58d41952fdf56c1/incs/INC-M2-001-mcp-cross-cli-imports.md` | Open INC in M2; substance deferred to sub-cycles |

---

## Three Future Sub-Cycles (from ADR-0057)

The M2 substance is recoverable as three future A-full sub-cycles:

### Sub-cycle 1: Close 4 unsanctioned ARCH-WIRING-001 hits

- **Scope**: Route `proposals.py:169`, `simulate.py:255`, `control_plane.py:3496`,
  `control_plane.py:3586` through `app.<method>` calls.
- **Gate**: `ARCH-WIRING-001`
- **ADR reference**: ADR-0057 § Promise 1

### Sub-cycle 2: Remove `world._arch_app` reverse-handle hack

- **Scope**: Route `status.py`, `ask.py`, `gate.py` through `app.status()`,
  `app.ask()`, `app.gate()`.
- **ADR reference**: ADR-0057 § Promise 3

### Sub-cycle 3: Add 6 wrappers to `bootstrap/__init__.py`

- **Scope**: `app.simulate`, `app.replay_fixture`, `app.distill_sensors`,
  `app.promote_sensor`, `app.reject_sensor`, `app.mine_conformance`.
- **ADR reference**: ADR-0057 § Promise 1 + ADR-0058

---

## Deferred to Verify Phase

This procedure is executed at the **verify-phase boundary**, NOT at apply phase,
per locked constraint #7 and the verify-boundary checklist (design.md §7 item 7.1).

The apply phase (this phase, Phase E) only creates this procedure document as
evidence. The actual `sddk cycle supersede` invocation is a verify-boundary action
dispatched by the orchestrator after all verify-phase checks pass.
