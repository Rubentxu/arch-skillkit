#!/usr/bin/env bats

# V2 seam tests: the Python Architecture World facade (python -m archskillkit).
# Cross-language contract: bash and python must resolve the same project id
# for the same repository; the repository stays untouched (UAT-001).

load 'test_helper'

setup() {
  new_sandbox
}

@test "v2: python resolves the same project id as the V1 bash helpers" {
  fixture_repo "$SB/repo" "https://github.com/rubentxu/fixture.git"

  expected="$(
    SCRIPTS="$SCRIPTS" REPO="$SB/repo" bash -c '
      source "$SCRIPTS/lib/common.sh"
      root="$(repo_root "$REPO")"
      remote="$(repo_remote "$root")"
      compute_project_id "$root" "$remote"
    '
  )"

  run run_world init --repo "$SB/repo"
  assert_rc "init rc" 0 "$status"
  got="$(printf '%s' "$output" | jq -r .project_id)"
  assert_eq "project id parity" "$expected" "$got"
}

@test "v2: observation lands in the world and replay reproduces it" {
  fixture_repo "$SB/repo" "https://github.com/rubentxu/fixture.git"

  run run_world init --repo "$SB/repo"
  assert_rc "init rc" 0 "$status"

  payload="$SB/obs.json"
  cat >"$payload" <<'JSON'
{"subject":"domain.orders","predicate":"exposes","object":"POST /orders",
 "evidence":{"tool":"semgrep","rule":"spring.endpoint","file":"Orders.kt","start_line":10}}
JSON
  run run_world record-observation --repo "$SB/repo" --payload "$payload"
  assert_rc "record rc" 0 "$status"

  run run_world state --repo "$SB/repo"
  assert_rc "state rc" 0 "$status"
  assert_output_contains "state has the observation" '"observation"' "$output"

  run run_world replay-verify --repo "$SB/repo"
  assert_rc "replay rc" 0 "$status"
  assert_output_contains "replay ok" "replay OK" "$output"
}

@test "v2: Architecture World keeps the repository untouched (UAT-001)" {
  fixture_repo "$SB/repo" "https://github.com/rubentxu/fixture.git"
  before="$(git -C "$SB/repo" status --porcelain)"

  run run_world init --repo "$SB/repo"
  assert_rc "init rc" 0 "$status"
  run run_world replay-verify --repo "$SB/repo"
  assert_rc "replay rc" 0 "$status"

  after="$(git -C "$SB/repo" status --porcelain)"
  assert_eq "repo untouched" "$before" "$after"
}

@test "v2: replay-verify on a project without world fails cleanly" {
  fixture_repo "$SB/repo" "https://github.com/rubentxu/fixture.git"
  run run_world replay-verify --repo "$SB/repo"
  assert_rc "replay rc" 1 "$status"
  assert_output_contains "actionable error" "no Architecture World" "$output"
}
