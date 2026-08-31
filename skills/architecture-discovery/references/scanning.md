# Scanning Role

Operates the deterministic scanners. The Scanning role runs tools and
preserves evidence; it never interprets architecture beyond trivial
metadata.

## Procedure

1. Verify the environment with `scripts/doctor.sh`.
2. Resolve the project workspace with `scripts/workspace.sh` (registers the
   repository and its external workspace if new).
3. Run `scripts/scan.sh` — it selects the applicable scanners and produces
   ONE run manifest:

   | Scanner | Script | Applicable when |
   |---|---|---|
   | `ast-grep-outline` | scan-outline.sh | always |
   | `semgrep-architecture` | scan-patterns.sh | always |
   | `build-metadata` | scan-build.sh | Cargo.toml / package.json / gradle / pom present |

4. Read the run manifest and the warnings; report what degraded and why.

## Rules

- One run per analysis: never let sub-scanners open their own manifests when
  orchestrating (`scan.sh --run-id` owns the lifecycle).
- A scanner that cannot run is recorded, never simulated: no findings may be
  invented to replace a missing capability (UAT-013).
- The repository is read-only: if `git status` changes, the run is invalid.
- Raw outputs stay raw: normalization is a deferred decision (docs/16 E1),
  not a scanning-time task.

## Outputs

- `evidence/raw/ast-grep.jsonl` — structural outline.
- `evidence/raw/semgrep.json` — architectural pattern matches.
- `evidence/raw/build/` — build-system metadata + provenance.
- Run manifest under `$XDG_STATE_HOME/arch-skillkit/runs/<run_id>/`.
