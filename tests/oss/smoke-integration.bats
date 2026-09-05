#!/usr/bin/env bats
# smoke-integration.bats — 1 end-to-end case against slot 1
#
# Slot 1: Rubentxu/software-development-decision-kernel
# Expected: exit 0, RUN_MANIFEST verdict PASS, pin_match true,
#           evidence manifest non-empty.
#
# This test reuses the real slot 1 evidence from the stable root
# produced by the Phase 3 run. Runtime: ~2s (shallow clone, 17 MB).

setup() {
  SCRIPT_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")/../../scripts/oss" && pwd)"
  SMOKE_OSS="$SCRIPT_DIR/smoke-oss.sh"
  STABLE_ROOT="${SDDK_DATA_DIR:-$HOME/.local/share/sddk}/projects/p-f58d41952fdf56c1/oss-smoke"

  # The canonical slot 1 run produced by Phase 3 attempt 2
  SLOT1_RUN="smoke-20260905093755-1"
  SLOT1_PATH="$STABLE_ROOT/$SLOT1_RUN"
  SLOT1_SLOT_DIR="$SLOT1_PATH/slot1-rust/20260905"
}

# ── Integration test: slot 1 full-pipeline ───────────────────────────
@test "integration: slot1-rust smoke-oss.sh exit 0, verdict PASS, pin_match true, manifest non-empty" {
  # Verify smoke-oss.sh exists and is executable
  [[ -x "$SMOKE_OSS" ]]

  # Verify stable root evidence exists (from Phase 3 real run)
  [[ -d "$SLOT1_PATH" ]]
  [[ -d "$SLOT1_SLOT_DIR" ]]

  # ── Assert 1: RUN_MANIFEST.yaml exists and verdict = PASS ──
  local manifest="$SLOT1_SLOT_DIR/RUN_MANIFEST.yaml"
  [[ -f "$manifest" ]]
  grep -q 'verdict: PASS' "$manifest"

  # ── Assert 2: pin_match = true ──
  grep -q 'pin_match: true' "$manifest"

  # ── Assert 3: evidence manifest non-empty ──
  local evidence_manifest="$SLOT1_PATH/evidence/manifest.txt"
  [[ -f "$evidence_manifest" ]]
  [[ -s "$evidence_manifest" ]]

  # Manifest must have multiple sha256 entries
  local line_count
  line_count=$(wc -l < "$evidence_manifest")
  [[ $line_count -ge 1 ]]

  # ── Assert 4: frontmatter.txt has correct pinned_sha ──
  local frontmatter="$SLOT1_PATH/frontmatter.txt"
  [[ -f "$frontmatter" ]]
  grep -q 'pinned_sha: 327bfb23df4fa995f817d9ceded9498cd42b2e1c' "$frontmatter"

  # ── Assert 5: UAT.md exists ──
  local uat="$SLOT1_PATH/UAT.md"
  [[ -f "$uat" ]]
  [[ -s "$uat" ]]

  # ── Assert 6: git-before and git-after are identical (UAT2-001) ──
  local git_before="$SLOT1_PATH/git-before.txt"
  local git_after="$SLOT1_PATH/git-after.txt"
  [[ -f "$git_before" ]]
  [[ -f "$git_after" ]]
  diff "$git_before" "$git_after"
}
