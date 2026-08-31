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

Steps 1–2 are automated by `scripts/workspace.sh` (repository detection, project identity, external workspace, registry). Step 5 runs `scripts/scan-outline.sh` (ast-grep outline), `scripts/scan-patterns.sh` (Semgrep architecture markers) and `scripts/scan-build.sh` (build-system metadata), all from the pinned toolchain in `runtime/mise.toml` plus per-project build tools. Step 6 opens a run with `scripts/run-manifest.sh start` and closes it with `finish --status success|partial|failed`. Verify the environment with `scripts/doctor.sh` before starting.
