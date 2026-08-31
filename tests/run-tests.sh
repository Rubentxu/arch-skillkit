#!/usr/bin/env bash
# UAT harness for the workspace layer (M1.1 exit criteria).
# No test framework: plain bash with sandboxed XDG roots per test.
#
# Fixture commits set RANDOM_GIT_COMMITTER_DISABLED=1 because the dev
# machine's git wrapper refuses to sign commits in remote-less (unclassified)
# repositories; on stock git installations the variable is simply ignored.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS="$ROOT/skills/architecture-discovery/scripts"

pass=0
fail=0

ok() { printf '  ok   %s\n' "$1"; pass=$((pass + 1)); }
ko() { printf '  FAIL %s\n' "$1"; fail=$((fail + 1)); }
assert_eq() {
  if [ "$2" = "$3" ]; then ok "$1"; else ko "$1 (expected [$2], got [$3])"; fi
}
assert_not_eq() {
  if [ "$2" != "$3" ]; then ok "$1"; else ko "$1 (both values are [$2])"; fi
}
assert_true() {
  # assert_true <desc> <command...> — command may read stdin.
  local desc="$1"
  shift
  if "$@"; then ok "$desc"; else ko "$desc"; fi
}
assert_rc() {
  # assert_rc <desc> <expected_rc> <actual_rc>
  if [ "$3" -eq "$2" ]; then ok "$1"; else ko "$1 (expected rc=$2, got rc=$3)"; fi
}
assert_file() {
  if [ -f "$2" ]; then ok "$1"; else ko "$1 (missing file: $2)"; fi
}

SB=""
new_sandbox() {
  SB="$(mktemp -d)"
  mkdir -p "$SB/config" "$SB/data" "$SB/state" "$SB/cache" "$SB/override" "$SB/emptybin"
}

# Runs workspace.sh inside the sandbox; extra args are forwarded.
run_workspace() {
  local dir="$1"
  shift
  (
    cd "$dir" || exit 9
    XDG_CONFIG_HOME="$SB/config" XDG_DATA_HOME="$SB/data" \
      XDG_STATE_HOME="$SB/state" XDG_CACHE_HOME="$SB/cache" \
      ARCH_SKILLKIT_HOME="${SB_OVERRIDE:-}" \
      "$SCRIPTS/workspace.sh" "$@"
  )
}

# Runs doctor.sh inside the sandbox. $1: optional PATH for the child process
# (used to simulate missing dependencies deterministically). bash is resolved
# up-front because the child PATH may not contain it.
BASH_BIN="$(command -v bash)"
run_doctor() {
  local use_path="${1:-$PATH}"
  (
    cd "$SB" || exit 9
    XDG_CONFIG_HOME="$SB/config" XDG_DATA_HOME="$SB/data" \
      XDG_STATE_HOME="$SB/state" XDG_CACHE_HOME="$SB/cache" \
      ARCH_SKILLKIT_HOME="${SB_OVERRIDE:-}" \
      PATH="$use_path" "$BASH_BIN" "$SCRIPTS/doctor.sh"
  )
}

fixture_repo() {
  # $1: path, $2: optional origin URL. Creates a repo with one commit.
  git init -q -b main "$1"
  printf 'fixture\n' >"$1/README.md"
  git -C "$1" add README.md
  RANDOM_GIT_COMMITTER_DISABLED=1 \
    git -C "$1" -c user.email=fixture@example.com -c user.name=fixture commit -qm "init"
  if [ -n "${2:-}" ]; then git -C "$1" remote add origin "$2"; fi
  return 0
}

# ---------------------------------------------------------------- UAT-001
test_repository_remains_clean() {
  printf 'UAT-001: repository remains clean\n'
  new_sandbox
  local repo="$SB/repo"
  fixture_repo "$repo"
  local before after
  before="$(git -C "$repo" status --porcelain)"
  run_workspace "$repo" >/dev/null
  after="$(git -C "$repo" status --porcelain)"
  assert_eq "git status identical after run (clean tree)" "$before" "$after"

  printf 'dirty\n' >"$repo/uncommitted.txt"
  before="$(git -C "$repo" status --porcelain)"
  run_workspace "$repo" >/dev/null
  after="$(git -C "$repo" status --porcelain)"
  assert_eq "git status identical after run (dirty tree)" "$before" "$after"
  # .git, README.md, uncommitted.txt
  assert_eq "no files added to the repository" "3" "$(find "$repo" -mindepth 1 -maxdepth 1 | wc -l)"
}

# ---------------------------------------------------------------- UAT-002
test_assets_live_in_external_workspace() {
  printf 'UAT-002: all assets under the external workspace\n'
  new_sandbox
  local repo="$SB/repo"
  fixture_repo "$repo"
  local listing_before listing_after pid json
  listing_before="$(find "$repo" -type f | sort)"
  json="$(run_workspace "$repo" --json)"
  listing_after="$(find "$repo" -type f | sort)"
  assert_eq "repository file list unchanged" "$listing_before" "$listing_after"

  pid="$(printf '%s' "$json" | jq -r .project_id)"
  assert_file "project.json in external workspace" "$SB/data/arch-skillkit/projects/$pid/project.json"
  local d
  for d in evidence/raw evidence/curated evidence/provenance knowledge likec4/views arrows reports exports; do
    assert_true "workspace dir $d exists" test -d "$SB/data/arch-skillkit/projects/$pid/$d"
  done
}

# ---------------------------------------------------------------- UAT-003
test_same_name_repos_are_isolated() {
  printf 'UAT-003: same-name repositories get isolated workspaces\n'
  new_sandbox
  fixture_repo "$SB/one/api"
  fixture_repo "$SB/two/api"
  local pid1 pid2
  pid1="$(run_workspace "$SB/one/api" --json | jq -r .project_id)"
  pid2="$(run_workspace "$SB/two/api" --json | jq -r .project_id)"
  assert_not_eq "project ids do not collide" "$pid1" "$pid2"
  assert_true "two isolated workspaces created" test -d "$SB/data/arch-skillkit/projects/$pid1" -a -d "$SB/data/arch-skillkit/projects/$pid2"
}

test_idempotent_rerun() {
  printf 'idempotency: rerun reuses project identity\n'
  new_sandbox
  fixture_repo "$SB/repo"
  local pid1 pid2
  pid1="$(run_workspace "$SB/repo" --json | jq -r .project_id)"
  pid2="$(run_workspace "$SB/repo" --json | jq -r .project_id)"
  assert_eq "same project id on rerun" "$pid1" "$pid2"
  assert_eq "registry holds exactly one entry" "1" "$(jq '.projects | length' "$SB/state/arch-skillkit/registry.json")"
}

test_move_repository_keeps_identity() {
  printf 'move: remote match keeps identity and updates root\n'
  new_sandbox
  fixture_repo "$SB/origin/widget" "https://example.com/acme/widget.git"
  local pid pid_after
  pid="$(run_workspace "$SB/origin/widget" --json | jq -r .project_id)"
  mv "$SB/origin/widget" "$SB/moved-widget"
  pid_after="$(run_workspace "$SB/moved-widget" --json | jq -r .project_id)"
  assert_eq "moved repository keeps its project id" "$pid" "$pid_after"
  assert_eq "registry root updated to new path" "$SB/moved-widget" \
    "$(jq -r --arg pid "$pid" '.projects[] | select(.project_id == $pid) | .root' "$SB/state/arch-skillkit/registry.json")"
  assert_true "move recorded in events log" grep -q "event=moved-repository" "$SB/state/arch-skillkit/events.log"
}

test_same_remote_shares_identity() {
  printf 'clones: same remote share logical identity\n'
  new_sandbox
  fixture_repo "$SB/checkout-a" "https://example.com/acme/widget.git"
  fixture_repo "$SB/checkout-b" "https://example.com/acme/widget.git"
  local pid_a pid_b
  pid_a="$(run_workspace "$SB/checkout-a" --json | jq -r .project_id)"
  pid_b="$(run_workspace "$SB/checkout-b" --json | jq -r .project_id)"
  assert_eq "both checkouts resolve to one project id" "$pid_a" "$pid_b"
}

test_override_root() {
  printf 'override: ARCH_SKILLKIT_HOME relocates the workspace root\n'
  new_sandbox
  fixture_repo "$SB/repo"
  SB_OVERRIDE="$SB/override" run_workspace "$SB/repo" >/dev/null
  local pid
  pid="$(jq -r '.projects[0].project_id' "$SB/state/arch-skillkit/registry.json")"
  assert_true "workspace created under override root" test -d "$SB/override/projects/$pid"
  assert_true "registry still under XDG state root" test -f "$SB/state/arch-skillkit/registry.json"
}

test_project_json_schema() {
  printf 'schema: project.json carries the contract fields\n'
  new_sandbox
  fixture_repo "$SB/repo" "https://example.com/acme/schema.git"
  local json
  json="$(run_workspace "$SB/repo" --json)"
  assert_eq "all seven contract fields present" "7" \
    "$(printf '%s' "$json" | jq '[.schema_version, .project_id, .root, .remote, .branch, .commit, .workspace | tostring] | length')"
  assert_eq "remote is normalized (scheme, user and .git folded away)" "example.com/acme/schema" "$(printf '%s' "$json" | jq -r .remote)"
  assert_eq "registry mirrors schema_version" "1" "$(jq '.schema_version' "$SB/state/arch-skillkit/registry.json")"
}

test_rejects_non_repository() {
  printf 'errors: non-repository input is rejected with an actionable message\n'
  new_sandbox
  mkdir -p "$SB/plain"
  local out rc
  out="$(run_workspace "$SB/plain" 2>&1)"
  rc=$?
  if [ "$rc" -ne 0 ]; then ok "exit code is non-zero (rc=$rc)"; else ko "exit code is non-zero"; fi
  assert_true "error message names the problem" grep -q "not inside a git work tree" <<<"$out"
}

test_doctor_smoke() {
  printf 'doctor: runs read-only and reports the resolved roots\n'
  new_sandbox
  local out rc
  out="$(run_doctor 2>&1)"
  assert_true "doctor reports resolved roots" grep -q "resolved roots" <<<"$out"

  out="$(run_doctor "$SB/emptybin" 2>&1)"
  rc=$?
  assert_rc "doctor exits 1 when required tools are missing" 1 "$rc"
  assert_true "doctor names the missing dependency" grep -q "MISSING" <<<"$out"
}

printf 'ArchSkillKit workspace UAT harness\n'
test_repository_remains_clean
test_assets_live_in_external_workspace
test_same_name_repos_are_isolated
test_idempotent_rerun
test_move_repository_keeps_identity
test_same_remote_shares_identity
test_override_root
test_project_json_schema
test_rejects_non_repository
test_doctor_smoke

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
