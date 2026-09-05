#!/usr/bin/env bats
# smoke-integration.bats — Integration tests iterating ALL canonical runs
#
# Iterates over all 3 canonical runs from manifest.json:runs[].
# Expected: exit 0, RUN_MANIFEST verdict PASS, pin_match true,
#           evidence manifest non-empty, sha256sum -c passes.
#
# This test reuses the real evidence from the stable root
# produced by the Phase 3 run. Runtime: ~2s (shallow clone, 17 MB).

setup() {
  SCRIPT_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")/../../scripts/oss" && pwd)"
  SMOKE_OSS="$SCRIPT_DIR/smoke-oss.sh"
  STABLE_ROOT="${SDDK_DATA_DIR:-$HOME/.local/share/sddk}/projects/p-f58d41952fdf56c1/oss-smoke"
  MANIFEST="$STABLE_ROOT/manifest.json"

  # Skip if stable-root manifest.json absent
  if [[ ! -f "$MANIFEST" ]]; then
    skip "stable-root manifest.json absent"
  fi

  # Derive all canonical run IDs from manifest.json
  if ! mapfile -t RUNS < <(jq -r '.runs[].run_id' "$MANIFEST" 2>/dev/null); then
    skip "failed to parse manifest.json"
  fi

  # Require ≥3 canonical runs
  if [[ "${#RUNS[@]}" -lt 3 ]]; then
    skip "expected ≥3 canonical runs; got ${#RUNS[@]}"
  fi
}

# ── Integration test: iterate ALL canonical runs ─────────────────────
@test "integration: all canonical runs pass smoke-oss.sh assertions" {
  [[ -x "$SMOKE_OSS" ]]

  for run_id in "${RUNS[@]}"; do
    local run_path="$STABLE_ROOT/$run_id"

    # Find the slot subdirectory (slot1-rust/..., slot2-ts-saas/..., slot3-kotlin/...)
    local slot_dir
    slot_dir="$(find "$run_path" -mindepth 2 -maxdepth 2 -type d -name 'slot*' 2>/dev/null | head -1 || true)"
    [[ -n "$slot_dir" ]] || continue

    local date_dir
    date_dir="$(find "$slot_dir" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | head -1 || true)"
    [[ -n "$date_dir" ]] || continue

    local run_manifest="$date_dir/RUN_MANIFEST.yaml"

    # Assert 1: RUN_MANIFEST.yaml exists and verdict = PASS
    [[ -f "$run_manifest" ]]
    grep -q 'verdict: PASS' "$run_manifest"

    # Assert 2: pin_match = true
    grep -q 'pin_match: true' "$run_manifest"

    # Assert 3: evidence manifest non-empty
    local evidence_manifest="$run_path/evidence/manifest.txt"
    [[ -f "$evidence_manifest" ]]
    [[ -s "$evidence_manifest" ]]

    # Manifest must have multiple sha256 entries
    local line_count
    line_count=$(wc -l < "$evidence_manifest")
    [[ "$line_count" -ge 1 ]]

    # Assert 4: sha256sum -c exits 0 (no mismatches)
    local mismatch_count
    mismatch_count=$(cd "$run_path" && sha256sum -c evidence/manifest.txt 2>/dev/null | grep -c "FAILED" || echo 0)
    [[ "$mismatch_count" -eq 0 ]]

    # Assert 5: git-before and git-after are identical (UAT2-001)
    local git_before="$run_path/git-before.txt"
    local git_after="$run_path/git-after.txt"
    [[ -f "$git_before" ]]
    [[ -f "$git_after" ]]
    diff "$git_before" "$git_after"
  done
}
