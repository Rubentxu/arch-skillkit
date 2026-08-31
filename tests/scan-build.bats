# Build metadata coverage (M2.3): build-system metadata as evidence.
# Seam: scan-build.sh CLI — exit code, evidence under evidence/raw/build/,
# run manifest outcome (success | partial) — repository untouched.
load 'test_helper'

setup() {
  new_sandbox
}

build_evidence_of() {
  local pid
  pid="$(jq -r --arg root "$1" '.projects[] | select(.root == $root) | .project_id' "$SB/state/arch-skillkit/registry.json")"
  printf '%s' "$SB/data/arch-skillkit/projects/$pid/evidence/raw/build"
}

@test "build: cargo metadata stored as evidence for rust projects" {
  make_fixture_repo "$SB/repo" rust-hexagonal
  run run_build "$SB/repo"
  [ "$status" -eq 0 ]
  local dir
  dir="$(build_evidence_of "$SB/repo")"
  assert_file "cargo-metadata.json exists" "$dir/cargo-metadata.json"
  assert_eq "package name resolved" "rust-hexagonal" \
    "$(jq -r '[.packages[] | select(.name == "rust-hexagonal")] | length' "$dir/cargo-metadata.json" | sed 's/^1$/rust-hexagonal/')"

  local manifest provenance
  manifest="$(manifest_of_last_run)"
  assert_eq "manifest status" "success" "$(jq -r .status "$manifest")"
  assert_eq "scanner recorded" "build-metadata" "$(jq -r '.scanners[0]' "$manifest")"
  provenance="$dir/build.provenance.json"
  assert_file "provenance exists" "$provenance"
  assert_eq "cargo entry scanned" "scanned" \
    "$(jq -r '.systems[] | select(.system == "cargo") | .status' "$provenance")"
  [ "$(jq -r '.systems[] | select(.system == "cargo") | .tool_version' "$provenance")" != "absent" ]
}

@test "build: package.json stored as evidence for node projects" {
  make_fixture_repo "$SB/repo" ts-node
  run run_build "$SB/repo"
  [ "$status" -eq 0 ]
  local dir
  dir="$(build_evidence_of "$SB/repo")"
  assert_file "npm-package.json exists" "$dir/npm-package.json"
  assert_eq "package name recorded" "ts-node-fixture" "$(jq -r .name "$dir/npm-package.json")"
  assert_eq "manifest status" "success" "$(jq -r .status "$(manifest_of_last_run)")"
}

@test "build: gradle project is detected but build scripts are not executed" {
  make_fixture_repo "$SB/repo" kotlin-spring
  run run_build "$SB/repo"
  [ "$status" -eq 0 ]
  local provenance
  provenance="$(build_evidence_of "$SB/repo")/build.provenance.json"
  assert_file "provenance exists" "$provenance"
  assert_eq "gradle entry detected" "detected" \
    "$(jq -r '.systems[] | select(.system == "gradle") | .status' "$provenance")"
  assert_eq "manifest stays success" "success" "$(jq -r .status "$(manifest_of_last_run)")"
}

@test "build: missing cargo tool degrades to partial" {
  make_fixture_repo "$SB/repo" rust-hexagonal
  # PATH without ~/.cargo/bin and asdf shims: cargo/npm/gradle unavailable,
  # git/jq/mise still present.
  run run_build_restricted "$SB/repo"
  [ "$status" -eq 0 ]
  local provenance manifest
  provenance="$(build_evidence_of "$SB/repo")/build.provenance.json"
  manifest="$(manifest_of_last_run)"
  assert_eq "cargo entry unavailable" "unavailable" \
    "$(jq -r '.systems[] | select(.system == "cargo") | .status' "$provenance")"
  assert_eq "manifest status partial" "partial" "$(jq -r .status "$manifest")"
  assert_output_contains "warns about cargo" "cargo not available" "$output"
}

@test "build: repository without build systems warns but succeeds" {
  fixture_repo "$SB/repo"
  run_workspace "$SB/repo" >/dev/null
  run run_build "$SB/repo"
  [ "$status" -eq 0 ]
  assert_output_contains "warns about no build systems" "no build systems detected" "$output"
  assert_eq "manifest status" "success" "$(jq -r .status "$(manifest_of_last_run)")"
}

@test "build: repository remains untouched" {
  make_fixture_repo "$SB/repo" rust-hexagonal
  local before after
  before="$(git -C "$SB/repo" status --porcelain)"
  run run_build "$SB/repo"
  [ "$status" -eq 0 ]
  after="$(git -C "$SB/repo" status --porcelain)"
  assert_eq "git status unchanged" "$before" "$after"
}
