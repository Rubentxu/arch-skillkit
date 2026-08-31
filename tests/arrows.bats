# Arrows projection coverage (M5.1/M5.2): evidence-derived exploratory graphs.
# Seam: export-arrows.sh CLI — exit code, .arrows files under workspace
# arrows/, arch-skillkit/arrows-v1 schema integrity — repository untouched.
# Views are generated ONLY when their evidence exists (docs/12).
load 'test_helper'

setup() {
  new_sandbox
}

arrows_dir_of() {
  local pid
  pid="$(jq -r --arg root "$1" '.projects[] | select(.root == $root) | .project_id' "$SB/state/arch-skillkit/registry.json")"
  printf '%s' "$SB/data/arch-skillkit/projects/$pid/arrows"
}

# every relationship endpoint must reference an existing node id
assert_graph_integrity() {
  local file="$1" bad
  bad="$(jq -r '([.nodes[].id] | sort) as $ids
    | [.relationships[]
       | select((.start as $s | $ids | index($s) | not) or (.end as $e | $ids | index($e) | not))
       | .id] | join(",")' "$file")"
  [ -z "$bad" ]
}

@test "arrows: rust repo gets overview and dependency projections" {
  make_fixture_repo "$SB/repo" rust-hexagonal
  run_scan_all "$SB/repo" >/dev/null
  run run_arrows "$SB/repo"
  [ "$status" -eq 0 ]
  local dir
  dir="$(arrows_dir_of "$SB/repo")"
  assert_file "overview.arrows exists" "$dir/overview.arrows"
  assert_file "dependencies.arrows exists" "$dir/dependencies.arrows"

  assert_eq "schema is declared" "arch-skillkit/arrows-v1" \
    "$(jq -r .schema "$dir/overview.arrows")"
  assert_eq "project node present" "rust-hexagonal" \
    "$(jq -r '[.nodes[] | select(.id == "project")] | length' "$dir/overview.arrows" | sed 's/^1$/rust-hexagonal/')"

  jq -e . "$dir/dependencies.arrows" >/dev/null
}

@test "arrows: npm dependency edge derived from package.json" {
  make_fixture_repo "$SB/repo" ts-node
  run_scan_all "$SB/repo" >/dev/null
  run run_arrows "$SB/repo"
  [ "$status" -eq 0 ]
  local dir deps
  dir="$(arrows_dir_of "$SB/repo")"
  deps="$dir/dependencies.arrows"
  assert_file "dependencies view exists" "$deps"
  assert_eq "external dependency node present" "1" \
    "$(jq -r '[.nodes[] | select(.labels[0] == "ExternalDependency" and .properties.name == "express")] | length' "$deps")"
  assert_eq "dependency edge present" "1" \
    "$(jq -r '[.relationships[] | select(.type == "DEPENDS_ON" and .end == "dep:npm:express")] | length' "$deps")"
}

@test "arrows: endpoints, messaging and data-access from pattern evidence" {
  make_fixture_repo "$SB/repo" kotlin-spring
  run_scan_all "$SB/repo" >/dev/null
  run run_arrows "$SB/repo"
  [ "$status" -eq 0 ]
  local dir
  dir="$(arrows_dir_of "$SB/repo")"

  assert_file "endpoints view" "$dir/endpoints.arrows"
  assert_eq "three endpoint nodes" "3" \
    "$(jq -r '[.nodes[] | select(.labels[0] == "Endpoint")] | length' "$dir/endpoints.arrows")"

  assert_file "messaging view" "$dir/messaging.arrows"
  assert_eq "one messaging node" "1" \
    "$(jq -r '[.nodes[] | select(.labels[0] == "MessagingConsumer")] | length' "$dir/messaging.arrows")"

  assert_file "data-access view" "$dir/data-access.arrows"
  assert_eq "one data-access node" "1" \
    "$(jq -r '[.nodes[] | select(.labels[0] == "DataAccess")] | length' "$dir/data-access.arrows")"

  for v in endpoints messaging data-access; do
    assert_graph_integrity "$dir/$v.arrows" ||
      { printf 'graph integrity failed: %s\n' "$v" >&2; false; }
  done
}

@test "arrows: views are generated only when evidence exists" {
  fixture_repo "$SB/repo"
  run_workspace "$SB/repo" >/dev/null
  run run_arrows "$SB/repo"
  [ "$status" -eq 0 ]
  local dir
  dir="$(arrows_dir_of "$SB/repo")"
  assert_file "overview always generated" "$dir/overview.arrows"
  [ ! -f "$dir/endpoints.arrows" ]
  [ ! -f "$dir/messaging.arrows" ]
  [ ! -f "$dir/data-access.arrows" ]
  [ ! -f "$dir/dependencies.arrows" ]
}

@test "arrows: repository remains untouched" {
  make_fixture_repo "$SB/repo" kotlin-spring
  run_scan_all "$SB/repo" >/dev/null
  local before after
  before="$(git -C "$SB/repo" status --porcelain)"
  run run_arrows "$SB/repo"
  [ "$status" -eq 0 ]
  after="$(git -C "$SB/repo" status --porcelain)"
  assert_eq "git status unchanged" "$before" "$after"
}
