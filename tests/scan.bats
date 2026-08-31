# Scan coverage (M2.1): deterministic structural outline via ast-grep.
# Seam: scan-outline.sh CLI — exit code, evidence files under the project
# workspace, run manifest outcome — with the source repository untouched.
# Fixtures carry known symbols as ground truth (no LLM involved).
load 'test_helper'

setup() {
  new_sandbox
  make_fixture_repo "$SB/repo" rust-hexagonal
}

# Creates a git repo from a repo fixture and registers it in the sandbox.
make_fixture_repo() {
  local dest="$1" name="$2"
  mkdir -p "$dest"
  cp -r "$ROOT/fixtures/$name/." "$dest/"
  git init -q -b main "$dest"
  git -C "$dest" add .
  RANDOM_GIT_COMMITTER_DISABLED=1 \
    git -C "$dest" -c user.email=fixture@example.com -c user.name=fixture commit -qm "init"
  run_workspace "$dest" >/dev/null
}

manifest_of_last_run() {
  local run_id
  run_id="$(find "$SB/state/arch-skillkit/runs" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort | tail -n 1)"
  printf '%s' "$SB/state/arch-skillkit/runs/$run_id/manifest.json"
}

@test "scan: rust outline produces raw evidence with known symbols" {
  run run_scan "$SB/repo"
  [ "$status" -eq 0 ]
  local pid evidence
  pid="$(jq -r --arg root "$SB/repo" '.projects[] | select(.root == $root) | .project_id' "$SB/state/arch-skillkit/registry.json")"
  evidence="$SB/data/arch-skillkit/projects/$pid/evidence/raw/ast-grep.jsonl"
  assert_file "evidence file exists" "$evidence"

  local symbols
  symbols="$(jq -r '[.ruleId, .text] | @tsv' "$evidence")"
  assert_output_contains "struct Order detected" "outline.rust.struct	Order" "$symbols"
  assert_output_contains "trait OrderRepository detected" "outline.rust.trait	OrderRepository" "$symbols"
  assert_output_contains "enum OrderStatus detected" "outline.rust.enum	OrderStatus" "$symbols"
  assert_output_contains "function open_repository detected" "outline.rust.function	open_repository" "$symbols"

  while IFS= read -r line; do
    printf '%s' "$line" | jq -e . >/dev/null || { fail_line="invalid JSONL: $line"; break; }
  done <"$evidence"
  [ -z "${fail_line:-}" ]
}

@test "scan: run manifest is opened, stamped and closed as success" {
  run run_scan "$SB/repo"
  [ "$status" -eq 0 ]
  local manifest
  manifest="$(manifest_of_last_run)"
  assert_file "manifest exists" "$manifest"
  assert_eq "manifest status" "success" "$(jq -r .status "$manifest")"
  assert_eq "scanner recorded" "ast-grep-outline" "$(jq -r '.scanners[0]' "$manifest")"
  [ -n "$(jq -r .ended_at "$manifest")" ]
  [ -n "$(jq -r .tools.ast_grep "$manifest")" ]
}

@test "scan: provenance records tool, rules checksum and commit" {
  run run_scan "$SB/repo"
  [ "$status" -eq 0 ]
  local pid provenance
  pid="$(jq -r --arg root "$SB/repo" '.projects[] | select(.root == $root) | .project_id' "$SB/state/arch-skillkit/registry.json")"
  provenance="$SB/data/arch-skillkit/projects/$pid/evidence/raw/ast-grep.provenance.json"
  assert_file "provenance exists" "$provenance"
  assert_eq "tool recorded" "ast-grep" "$(jq -r .tool "$provenance")"
  [ "$(jq -r .tool_version "$provenance")" != "absent" ]
  assert_eq "commit recorded" "$(git -C "$SB/repo" rev-parse HEAD)" "$(jq -r .commit "$provenance")"
  [ -n "$(jq -r .rules_checksum "$provenance")" ]
  [ -n "$(jq -r .run_id "$provenance")" ]
}

@test "scan: typescript outline detects classes, interfaces and functions" {
  make_fixture_repo "$SB/repo" ts-node
  run run_scan "$SB/repo"
  [ "$status" -eq 0 ]
  local pid evidence symbols
  pid="$(jq -r --arg root "$SB/repo" '.projects[] | select(.root == $root) | .project_id' "$SB/state/arch-skillkit/registry.json")"
  evidence="$SB/data/arch-skillkit/projects/$pid/evidence/raw/ast-grep.jsonl"
  symbols="$(jq -r '[.ruleId, .text] | @tsv' "$evidence")"
  assert_output_contains "class detected" "outline.typescript.class	OrdersController" "$symbols"
  assert_output_contains "interface detected" "outline.typescript.interface	OrderRepository" "$symbols"
  assert_output_contains "function detected" "outline.typescript.function	createApp" "$symbols"
}

@test "scan: kotlin outline detects types and functions" {
  make_fixture_repo "$SB/repo" kotlin-spring
  run run_scan "$SB/repo"
  [ "$status" -eq 0 ]
  local pid evidence symbols
  pid="$(jq -r --arg root "$SB/repo" '.projects[] | select(.root == $root) | .project_id' "$SB/state/arch-skillkit/registry.json")"
  evidence="$SB/data/arch-skillkit/projects/$pid/evidence/raw/ast-grep.jsonl"
  symbols="$(jq -r '[.ruleId, .text] | @tsv' "$evidence")"
  assert_output_contains "type OrdersController detected" "outline.kotlin.type	OrdersController" "$symbols"
  assert_output_contains "type Order detected" "outline.kotlin.type	Order" "$symbols"
  assert_output_contains "function bootstrap detected" "outline.kotlin.function	bootstrap" "$symbols"
}

@test "scan: unregistered repo fails" {
  local dest="$SB/plain-rust"
  mkdir -p "$dest"
  cp -r "$ROOT/fixtures/rust-hexagonal/." "$dest/"
  git init -q -b main "$dest"
  git -C "$dest" add .
  RANDOM_GIT_COMMITTER_DISABLED=1 git -C "$dest" -c user.email=f@e.c -c user.name=f commit -qm init
  run run_scan "$dest"
  assert_rc "unregistered rejected" 1 "$status"
  assert_output_contains "guidance present" "run workspace.sh first" "$output"
}

@test "scan: repo without supported sources warns but succeeds" {
  local dest="$SB/empty-go"
  mkdir -p "$dest"
  printf 'package main\nfunc main() {}\n' >"$dest/main.go"
  git init -q -b main "$dest"
  git -C "$dest" add .
  RANDOM_GIT_COMMITTER_DISABLED=1 git -C "$dest" -c user.email=f@e.c -c user.name=f commit -qm init
  run_workspace "$dest" >/dev/null
  run run_scan "$dest"
  [ "$status" -eq 0 ]
  assert_output_contains "warns about no matches" "no structural outline matches" "$output"
  local manifest
  manifest="$(manifest_of_last_run)"
  assert_eq "manifest still success" "success" "$(jq -r .status "$manifest")"
}

@test "scan: repository remains untouched" {
  local repo="$SB/repo"
  local before after
  before="$(git -C "$repo" status --porcelain)"
  run run_scan "$repo"
  [ "$status" -eq 0 ]
  after="$(git -C "$repo" status --porcelain)"
  assert_eq "git status unchanged" "$before" "$after"
}
