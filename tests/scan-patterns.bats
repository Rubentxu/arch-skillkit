# Pattern scan coverage (M2.2): architectural pattern detection via Semgrep.
# Seam: scan-patterns.sh CLI — exit code, evidence files under the project
# workspace, run manifest outcome — with the source repository untouched.
# Fixtures carry labeled positive/negative cases as ground truth.
load 'test_helper'

setup() {
  new_sandbox
}

patterns_evidence_of() {
  local pid
  pid="$(jq -r --arg root "$1" '.projects[] | select(.root == $root) | .project_id' "$SB/state/arch-skillkit/registry.json")"
  printf '%s' "$SB/data/arch-skillkit/projects/$pid/evidence/raw/semgrep.json"
}

@test "patterns: kotlin spring endpoints, messaging and persistence detected" {
  make_fixture_repo "$SB/repo" kotlin-spring
  run run_patterns "$SB/repo"
  [ "$status" -eq 0 ]
  local evidence
  evidence="$(patterns_evidence_of "$SB/repo")"
  assert_file "semgrep.json exists" "$evidence"
  jq -e . "$evidence" >/dev/null

  assert_eq "three endpoints detected" "3" \
    "$(jq -r '[.results[] | select(.check_id == "spring.endpoint")] | length' "$evidence")"
  assert_eq "one messaging listener detected" "1" \
    "$(jq -r '[.results[] | select(.check_id == "spring.messaging.listener")] | length' "$evidence")"
  assert_eq "one repository detected" "1" \
    "$(jq -r '[.results[] | select(.check_id == "spring.persistence.repository")] | length' "$evidence")"
  assert_eq "no matches on labeled negatives" "0" \
    "$(jq -r '[.results[] | select(.path | endswith("Negatives.kt"))] | length' "$evidence")"
}

@test "patterns: run manifest records scanner and finishes as success" {
  make_fixture_repo "$SB/repo" kotlin-spring
  run run_patterns "$SB/repo"
  [ "$status" -eq 0 ]
  local manifest
  manifest="$(manifest_of_last_run)"
  assert_eq "manifest status" "success" "$(jq -r .status "$manifest")"
  assert_eq "scanner recorded" "semgrep-architecture" "$(jq -r '.scanners[0]' "$manifest")"
  [ "$(jq -r .tools.semgrep "$manifest")" != "absent" ]
  [ -n "$(jq -r .ended_at "$manifest")" ]
}

@test "patterns: provenance records tool, rules checksum and commit" {
  make_fixture_repo "$SB/repo" kotlin-spring
  run run_patterns "$SB/repo"
  [ "$status" -eq 0 ]
  local pid provenance
  pid="$(jq -r --arg root "$SB/repo" '.projects[] | select(.root == $root) | .project_id' "$SB/state/arch-skillkit/registry.json")"
  provenance="$SB/data/arch-skillkit/projects/$pid/evidence/raw/semgrep.provenance.json"
  assert_file "provenance exists" "$provenance"
  assert_eq "tool recorded" "semgrep" "$(jq -r .tool "$provenance")"
  assert_eq "commit recorded" "$(git -C "$SB/repo" rev-parse HEAD)" "$(jq -r .commit "$provenance")"
  [ -n "$(jq -r .rules_checksum "$provenance")" ]
}

@test "patterns: typescript express endpoints detected" {
  make_fixture_repo "$SB/repo" ts-node
  run run_patterns "$SB/repo"
  [ "$status" -eq 0 ]
  local evidence
  evidence="$(patterns_evidence_of "$SB/repo")"
  assert_eq "three express endpoints detected" "3" \
    "$(jq -r '[.results[] | select(.check_id == "express.endpoint")] | length' "$evidence")"
  assert_eq "loose get/post receivers not matched" "0" \
    "$(jq -r '[.results[] | select(.path | endswith("app.ts")) | select(.start.line >= 13)] | length' "$evidence")"
}

@test "patterns: rust actix endpoints and reqwest client detected" {
  make_fixture_repo "$SB/repo" rust-hexagonal
  run run_patterns "$SB/repo"
  [ "$status" -eq 0 ]
  local evidence
  evidence="$(patterns_evidence_of "$SB/repo")"
  assert_eq "two actix endpoints detected" "2" \
    "$(jq -r '[.results[] | select(.check_id == "actix.endpoint")] | length' "$evidence")"
  assert_eq "one reqwest client detected" "1" \
    "$(jq -r '[.results[] | select(.check_id == "http.client.reqwest")] | length' "$evidence")"
}

@test "patterns: unregistered repo fails" {
  local dest="$SB/plain"
  mkdir -p "$dest/src"
  printf 'fun main() {}\n' >"$dest/src/Main.kt"
  git init -q -b main "$dest"
  git -C "$dest" add .
  RANDOM_GIT_COMMITTER_DISABLED=1 git -C "$dest" -c user.email=f@e.c -c user.name=f commit -qm init
  run run_patterns "$dest"
  assert_rc "unregistered rejected" 1 "$status"
  assert_output_contains "guidance present" "run workspace.sh first" "$output"
}

@test "patterns: repository remains untouched" {
  make_fixture_repo "$SB/repo" kotlin-spring
  local before after
  before="$(git -C "$SB/repo" status --porcelain)"
  run run_patterns "$SB/repo"
  [ "$status" -eq 0 ]
  after="$(git -C "$SB/repo" status --porcelain)"
  assert_eq "git status unchanged" "$before" "$after"
}
