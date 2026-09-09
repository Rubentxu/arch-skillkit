# M2 WIP Branches — Superseded

> **Status**: ARCHIVED (preserved as git tags for audit trail)
> **Superseded by**: PR #2 (v0.10.0), released 2026-09-08

## Why archived

Two work-in-progress branches accumulated during the v2.5 M2 cycle:

- **`feat/m2-cherrypick`** — an early cherry-pick attempt onto v0.9.0 base.
  Contained 3 commits:
    - `79e122a` Phase C migration with fallback
    - `03d0e02` cherry-pick onto v0.9.0 base
    - `b22d5f6` restore `world` context manager in `status.handle()`
- **`feat/m2-composition-root-delivery-closure`** — the upstream M2 cycle
  branch that produced the original composition-root work (proposals,
  simulate, ask, gate routed through `ArchSkillKitApplication`).

Both branches were superseded by the **deliberate cherry-pick in v0.10.0**
(PR #2, commit `f4c74ef`), which selected only the production-ready slices
from `feat/m2-composition-root-delivery-closure` and applied them onto the
v0.9.0 baseline.

The cherry-pick was deliberate: the original branch carried partial work
that we wanted to integrate surgically rather than merge wholesale.

## What landed in main

The work that survived the cherry-pick is in `f4c74ef` (PR #2):

- 4 application services created (proposal, sensor, replay, conformance)
- 4 application tests
- Phase A: route `proposals` through `app.<method>()`
- Phase B: route `status`, `ask`, `gate`, `simulate` through app
- Phase C: complete migration with fallback for direct CLI invocation
- Plus `b22d5f6` (the `world` context manager fix cherry-picked separately)

## What's preserved here

The two WIP branches are preserved as git tags:

```bash
git log archive/feat-m2-cherrypick          # full WIP history of cherry-pick branch
git log archive/feat-m2-composition-root-delivery-closure  # full upstream M2 history
```

The branches themselves were deleted locally and remotely
(`feat/m2-cherrypick` had a remote counterpart; `feat/m2-composition-root-delivery-closure`
was local-only). The tags make the history recoverable without leaving
dead branches in the repo.

## Migration recipe (for future WIP cleanup)

1. `git tag archive/<short-name> <branch>` to preserve the ref history.
2. `git branch -D <branch>` for local cleanup.
3. `git push origin :<branch>` for remote cleanup (if applicable).
4. Add a SUPERSEDE-NOTICE.md documenting:
   - the cycle that superseded the WIP branch,
   - which commits survived and where they live in main,
   - how to recover the original history (via the tag).

## Refs

- PR #2: https://github.com/Rubentxu/arch-skillkit/pull/2
- Issue #1: https://github.com/Rubentxu/arch-skillkit/issues/1
- v0.10.0 release: https://github.com/Rubentxu/arch-skillkit/releases/tag/v0.10.0
- v0.12.0 (current release): APP-COVERAGE 1.0 after M3 closure
