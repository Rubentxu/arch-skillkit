# Run manifest lifecycle (docs/15): what ran, with which versions, against
# which commit, and with which outcome.
# Seam: run-manifest.sh CLI — start/finish — and the manifest.json it
# produces under $XDG_STATE_HOME/arch-skillkit/runs/<run_id>/.
load 'test_helper'

setup() {
  new_sandbox
  fixture_repo "$SB/repo" "https://example.com/acme/widget.git"
}

register_project() {
  run_workspace "$SB/repo" >/dev/null
}

@test "start: creates a running manifest and prints its run id" {
  register_project
  run run_manifest start --repo "$SB/repo"
  [ "$status" -eq 0 ]
  local run_id="$output"
  [[ "$run_id" =~ ^[0-9]{8}T[0-9]{6}Z-[0-9]+$ ]]
  local manifest="$SB/state/arch-skillkit/runs/$run_id/manifest.json"
  assert_file "manifest.json exists" "$manifest"
  assert_eq "status is running" "running" "$(jq -r .status "$manifest")"
  assert_eq "project_id recorded" \
    "$(jq -r '.projects[0].project_id' "$SB/state/arch-skillkit/registry.json")" \
    "$(jq -r .project_id "$manifest")"
  assert_eq "commit recorded" "$(git -C "$SB/repo" rev-parse HEAD)" "$(jq -r .commit "$manifest")"
  [ -n "$(jq -r .started_at "$manifest")" ]
  [ "$(jq -r '[.run_id, .skill_version, .tools.git, .tools.jq, .scanners, .warnings, .errors] | length' "$manifest")" -eq 7 ]
}

@test "finish: marks the run with a final status and end timestamp" {
  register_project
  local run_id
  run_id="$(run_manifest start --repo "$SB/repo")"
  run run_manifest finish "$run_id" --status success
  [ "$status" -eq 0 ]
  local manifest="$SB/state/arch-skillkit/runs/$run_id/manifest.json"
  assert_eq "status is success" "success" "$(jq -r .status "$manifest")"
  [ -n "$(jq -r .ended_at "$manifest")" ]
}

@test "finish: unknown run id is rejected with an actionable message" {
  run run_manifest finish "20990101T000000Z-999999" --status success
  assert_rc "unknown run id fails" 1 "$status"
  assert_output_contains "error names the problem" "unknown run id" "$output"
}

@test "finish: invalid status value is rejected" {
  register_project
  local run_id
  run_id="$(run_manifest start --repo "$SB/repo")"
  run run_manifest finish "$run_id" --status triumphant
  assert_rc "invalid status fails" 2 "$status"
  assert_eq "manifest still running" "running" \
    "$(jq -r .status "$SB/state/arch-skillkit/runs/$run_id/manifest.json")"
}

@test "finish: finishing twice is rejected" {
  register_project
  local run_id
  run_id="$(run_manifest start --repo "$SB/repo")"
  run run_manifest finish "$run_id" --status success
  [ "$status" -eq 0 ]
  run run_manifest finish "$run_id" --status failed
  assert_rc "double finish fails" 1 "$status"
  assert_output_contains "error names the problem" "already finished" "$output"
  assert_eq "status stays success" "success" \
    "$(jq -r .status "$SB/state/arch-skillkit/runs/$run_id/manifest.json")"
}

@test "start: unregistered repository is rejected with guidance" {
  run run_manifest start --repo "$SB/repo"
  assert_rc "unregistered repo fails" 1 "$status"
  assert_output_contains "error names the remedy" "run workspace.sh first" "$output"
}
