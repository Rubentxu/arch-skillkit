# Workflow

1. Resolve repository root and project identity.
2. Resolve/create external project workspace.
3. Record initial `git status --porcelain`.
4. Discover languages/build systems.
5. Run applicable deterministic scanners.
6. Persist raw evidence and run manifest.
7. Perform architecture discovery from evidence.
8. Open source files only for unresolved questions.
9. Update LikeC4 conservatively.
10. Generate relevant Arrows projections.
11. Run reviewer pass.
12. Validate LikeC4.
13. Compare final Git status with initial status.
14. Write report and unresolved assumptions.

## Tooling

Steps 1–2 are automated by `scripts/workspace.sh` (repository detection, project identity, external workspace, registry). Steps 3–6 run as one orchestrated scan via `scripts/scan.sh` (single run manifest; see `references/scanning.md`). Verify the environment with `scripts/doctor.sh` before starting.

## Roles

- Steps 1–6: the Scanner role (`references/scanning.md`).
- Steps 7–8: the Discovery role (`references/discovery.md`).
- Steps 9–10 and 12: the Modeler role (`references/modeling-policy.md`).
- Steps 11, 13 and 14: the Review role (`references/review.md`).
