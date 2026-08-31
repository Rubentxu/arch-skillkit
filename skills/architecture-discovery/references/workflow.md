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
