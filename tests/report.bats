# Organized viewing coverage: report index with mermaid diagrams and the
# project registry index. Seam: report.sh / projects.sh CLI outputs.
load 'test_helper'

setup() {
  new_sandbox
}

reports_dir_of() {
  local pid
  pid="$(jq -r --arg root "$1" '.projects[] | select(.root == $root) | .project_id' "$SB/state/arch-skillkit/registry.json")"
  printf '%s' "$SB/data/arch-skillkit/projects/$pid/reports"
}

@test "report: index.md organizes evidence, diagrams and model status" {
  make_fixture_repo "$SB/repo" rust-hexagonal
  run_scan_all "$SB/repo" >/dev/null
  run_arrows "$SB/repo" >/dev/null
  cp "$SCRIPTS/../templates/model.c4" \
    "$SB/data/arch-skillkit/projects/$(jq -r --arg root "$SB/repo" '.projects[] | select(.root == $root) | .project_id' "$SB/state/arch-skillkit/registry.json")/likec4/model.c4"

  run run_report "$SB/repo"
  [ "$status" -eq 0 ]
  local index
  index="$(reports_dir_of "$SB/repo")/index.md"
  assert_file "index.md exists" "$index"
  assert_output_contains "project named" "rust-hexagonal" "$(cat "$index")"
  assert_output_contains "evidence section" "Evidence summary" "$(cat "$index")"
  assert_output_contains "mermaid diagram embedded" '```mermaid' "$(cat "$index")"
  assert_output_contains "model status present" "model" "$(cat "$index")"
  assert_output_contains "view commands present" "likec4 serve" "$(cat "$index")"
}

@test "report: kotlin endpoints view produces a mermaid diagram with edges" {
  make_fixture_repo "$SB/repo" kotlin-spring
  run_scan_all "$SB/repo" >/dev/null
  run_arrows "$SB/repo" >/dev/null
  run run_report "$SB/repo"
  [ "$status" -eq 0 ]
  local index
  index="$(reports_dir_of "$SB/repo")/index.md"
  assert_output_contains "endpoints diagram section" "Endpoints" "$(cat "$index")"
  assert_output_contains "edges rendered" "DECLARED_IN" "$(cat "$index")"
}

@test "report: works without model or arrows (scan only)" {
  make_fixture_repo "$SB/repo" rust-hexagonal
  run_scan_all "$SB/repo" >/dev/null
  run run_report "$SB/repo"
  [ "$status" -eq 0 ]
  local index
  index="$(reports_dir_of "$SB/repo")/index.md"
  assert_file "index.md exists" "$index"
  assert_output_contains "no-model stated" "no model" "$(cat "$index")"
}

@test "projects: registry index lists registered projects with status" {
  make_fixture_repo "$SB/repo" rust-hexagonal
  run_scan_all "$SB/repo" >/dev/null
  fixture_repo "$SB/other"
  run_workspace "$SB/other" >/dev/null

  run run_projects
  [ "$status" -eq 0 ]
  assert_output_contains "lists first project" "repo-" "$output"
  assert_output_contains "lists other project" "other-" "$output"
  assert_output_contains "shows scan status" "success" "$output"
}
