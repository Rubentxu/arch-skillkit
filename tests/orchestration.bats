# Orchestration coverage (M3.1): the Scanner role selects applicable
# scanners per repository and produces ONE run manifest.
# Seam: scan.sh CLI — exit code, evidence files, single-run manifest with
# recorded scanners, aggregate status — repository untouched.
load 'test_helper'

setup() {
  new_sandbox
}

@test "orchestration: one run manifest records all scanners on a rust repo" {
  make_fixture_repo "$SB/repo" rust-hexagonal
  run run_scan_all "$SB/repo"
  [ "$status" -eq 0 ]

  local n_runs
  n_runs="$(find "$SB/state/arch-skillkit/runs" -mindepth 1 -maxdepth 1 -type d | wc -l)"
  assert_eq "exactly one run manifest" "1" "$n_runs"

  local manifest
  manifest="$(manifest_of_last_run)"
  assert_eq "manifest status" "success" "$(jq -r .status "$manifest")"
  assert_eq "scanners recorded" "ast-grep-outline semgrep-architecture build-metadata" \
    "$(jq -r '.scanners | join(" ")' "$manifest")"

  local pid evidence
  pid="$(jq -r --arg root "$SB/repo" '.projects[] | select(.root == $root) | .project_id' "$SB/state/arch-skillkit/registry.json")"
  evidence="$SB/data/arch-skillkit/projects/$pid/evidence/raw"
  assert_file "outline evidence" "$evidence/ast-grep.jsonl"
  assert_file "pattern evidence" "$evidence/semgrep.json"
  assert_file "build evidence" "$evidence/build/cargo-metadata.json"
}

@test "orchestration: selects scanners per repository (no build files)" {
  fixture_repo "$SB/repo"
  printf 'fun main() {}\n' >"$SB/repo/Main.kt"
  git -C "$SB/repo" add Main.kt
  RANDOM_GIT_COMMITTER_DISABLED=1 \
    git -C "$SB/repo" -c user.email=fixture@example.com -c user.name=fixture commit -qm "add main"
  run_workspace "$SB/repo" >/dev/null

  run run_scan_all "$SB/repo"
  [ "$status" -eq 0 ]
  local manifest
  manifest="$(manifest_of_last_run)"
  assert_eq "build scanner not applicable" "ast-grep-outline semgrep-architecture" \
    "$(jq -r '.scanners | join(" ")' "$manifest")"
  assert_eq "aggregate status" "success" "$(jq -r .status "$manifest")"
}

@test "orchestration: kotlin repo aggregates outline, patterns and gradle detection" {
  make_fixture_repo "$SB/repo" kotlin-spring
  run run_scan_all "$SB/repo"
  [ "$status" -eq 0 ]
  local manifest
  manifest="$(manifest_of_last_run)"
  assert_eq "manifest status" "success" "$(jq -r .status "$manifest")"
  assert_eq "scanners recorded" "ast-grep-outline semgrep-architecture build-metadata" \
    "$(jq -r '.scanners | join(" ")' "$manifest")"
}

@test "orchestration: repository remains untouched" {
  make_fixture_repo "$SB/repo" rust-hexagonal
  local before after
  before="$(git -C "$SB/repo" status --porcelain)"
  run run_scan_all "$SB/repo"
  [ "$status" -eq 0 ]
  after="$(git -C "$SB/repo" status --porcelain)"
  assert_eq "git status unchanged" "$before" "$after"
}
