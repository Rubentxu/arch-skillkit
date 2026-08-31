# UAT coverage for the workspace layer (M1.1 exit criteria).
# Seam: workspace.sh CLI — exit code, output and effects under the resolved
# XDG roots — with the source repository left untouched.
load 'test_helper'

setup() {
  new_sandbox
}

@test "UAT-001: git status identical after run (clean tree)" {
  local repo="$SB/repo"
  fixture_repo "$repo"
  local before after
  before="$(git -C "$repo" status --porcelain)"
  run run_workspace "$repo"
  [ "$status" -eq 0 ]
  after="$(git -C "$repo" status --porcelain)"
  assert_eq "git status unchanged" "$before" "$after"
}

@test "UAT-001: git status identical after run (dirty tree)" {
  local repo="$SB/repo"
  fixture_repo "$repo"
  printf 'dirty\n' >"$repo/uncommitted.txt"
  local before after
  before="$(git -C "$repo" status --porcelain)"
  run run_workspace "$repo"
  [ "$status" -eq 0 ]
  after="$(git -C "$repo" status --porcelain)"
  assert_eq "git status unchanged" "$before" "$after"
}

@test "UAT-001: no files added to the repository" {
  local repo="$SB/repo"
  fixture_repo "$repo"
  printf 'dirty\n' >"$repo/uncommitted.txt"
  run run_workspace "$repo"
  # .git, README.md, uncommitted.txt
  assert_eq "repository top-level entries" "3" "$(find "$repo" -mindepth 1 -maxdepth 1 | wc -l)"
}

@test "UAT-002: repository file list unchanged" {
  local repo="$SB/repo"
  fixture_repo "$repo"
  local listing_before
  listing_before="$(find "$repo" -type f | sort)"
  run run_workspace "$repo" --json
  [ "$status" -eq 0 ]
  assert_eq "repository file list unchanged" "$listing_before" "$(find "$repo" -type f | sort)"
}

@test "UAT-002: project.json lives in the external workspace" {
  local repo="$SB/repo"
  fixture_repo "$repo"
  run run_workspace "$repo" --json
  [ "$status" -eq 0 ]
  local pid
  pid="$(printf '%s' "$output" | jq -r .project_id)"
  assert_file "project.json in external workspace" "$SB/data/arch-skillkit/projects/$pid/project.json"
}

@test "UAT-002: workspace scaffold directories exist" {
  local repo="$SB/repo"
  fixture_repo "$repo"
  run run_workspace "$repo" --json
  local pid
  pid="$(printf '%s' "$output" | jq -r .project_id)"
  local d
  for d in evidence/raw evidence/curated evidence/provenance knowledge likec4/views arrows reports exports; do
    assert_dir "workspace dir $d" "$SB/data/arch-skillkit/projects/$pid/$d"
  done
}

@test "UAT-003: same-name repositories get isolated workspaces" {
  fixture_repo "$SB/one/api"
  fixture_repo "$SB/two/api"
  local pid1 pid2
  pid1="$(run_workspace "$SB/one/api" --json | jq -r .project_id)"
  pid2="$(run_workspace "$SB/two/api" --json | jq -r .project_id)"
  assert_not_eq "project ids do not collide" "$pid1" "$pid2"
  assert_dir "workspace one" "$SB/data/arch-skillkit/projects/$pid1"
  assert_dir "workspace two" "$SB/data/arch-skillkit/projects/$pid2"
}

@test "idempotency: rerun reuses project identity and registry entry" {
  local repo="$SB/repo"
  fixture_repo "$repo"
  local pid1 pid2
  pid1="$(run_workspace "$repo" --json | jq -r .project_id)"
  pid2="$(run_workspace "$repo" --json | jq -r .project_id)"
  assert_eq "same project id on rerun" "$pid1" "$pid2"
  assert_eq "registry holds exactly one entry" "1" \
    "$(jq '.projects | length' "$SB/state/arch-skillkit/registry.json")"
}

@test "move: remote match keeps identity and updates root" {
  fixture_repo "$SB/origin/widget" "https://example.com/acme/widget.git"
  local pid
  pid="$(run_workspace "$SB/origin/widget" --json | jq -r .project_id)"
  mv "$SB/origin/widget" "$SB/moved-widget"
  local pid_after
  pid_after="$(run_workspace "$SB/moved-widget" --json | jq -r .project_id)"
  assert_eq "moved repository keeps its project id" "$pid" "$pid_after"
  assert_eq "registry root updated to new path" "$SB/moved-widget" \
    "$(jq -r --arg pid "$pid" '.projects[] | select(.project_id == $pid) | .root' "$SB/state/arch-skillkit/registry.json")"
  assert_file "events log exists" "$SB/state/arch-skillkit/events.log"
  assert_output_contains "move recorded in events log" "event=moved-repository" \
    "$(cat "$SB/state/arch-skillkit/events.log")"
}

@test "clones: same remote shares logical identity" {
  fixture_repo "$SB/checkout-a" "https://example.com/acme/widget.git"
  fixture_repo "$SB/checkout-b" "https://example.com/acme/widget.git"
  local pid_a pid_b
  pid_a="$(run_workspace "$SB/checkout-a" --json | jq -r .project_id)"
  pid_b="$(run_workspace "$SB/checkout-b" --json | jq -r .project_id)"
  assert_eq "both checkouts resolve to one project id" "$pid_a" "$pid_b"
}

@test "override: ARCH_SKILLKIT_HOME relocates the workspace root" {
  local repo="$SB/repo"
  fixture_repo "$repo"
  SB_OVERRIDE="$SB/override" run run_workspace "$repo" >/dev/null
  local pid
  pid="$(jq -r '.projects[0].project_id' "$SB/state/arch-skillkit/registry.json")"
  assert_dir "workspace under override root" "$SB/override/projects/$pid"
  assert_file "registry still under XDG state root" "$SB/state/arch-skillkit/registry.json"
}

@test "schema: project.json carries the seven contract fields" {
  local repo="$SB/repo"
  fixture_repo "$repo" "https://example.com/acme/schema.git"
  local json
  json="$(run_workspace "$repo" --json)"
  assert_eq "field count" "7" \
    "$(printf '%s' "$json" | jq '[.schema_version, .project_id, .root, .remote, .branch, .commit, .workspace | tostring] | length')"
  assert_eq "remote is normalized" "example.com/acme/schema" "$(printf '%s' "$json" | jq -r .remote)"
  assert_eq "registry schema_version" "1" "$(jq '.schema_version' "$SB/state/arch-skillkit/registry.json")"
}

@test "errors: non-repository input is rejected with an actionable message" {
  mkdir -p "$SB/plain"
  run run_workspace "$SB/plain"
  assert_rc "non-repository rejected" 1 "$status"
  assert_output_contains "error names the problem" "not inside a git work tree" "$output"
}
