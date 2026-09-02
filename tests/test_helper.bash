# Shared helpers for the BATS suites (loaded via `load 'test_helper'`).
#
# Seams under test: each script's CLI — exit code, stdout and filesystem
# effects under the resolved XDG roots — with the source repository left
# untouched. Tests never reach into script internals.

ROOT="$(cd "$BATS_TEST_DIRNAME/.." && pwd)"
SCRIPTS="$ROOT/skills/architecture-discovery/scripts"

SB=""

new_sandbox() {
  # Per-test XDG roots. $BATS_TEST_TMPDIR is fresh for every @test.
  SB="$BATS_TEST_TMPDIR"
  mkdir -p "$SB/config" "$SB/data" "$SB/state" "$SB/cache" "$SB/override" "$SB/emptybin"
}

# Resolve ast-grep from PATH or the mise-installed path. Returns the
# absolute path or empty. Used by the smoke suite to invoke the
# scanner binary without hard-coding the mise install location.
find_ast_grep() {
  if command -v ast-grep >/dev/null 2>&1; then
    command -v ast-grep
    return 0
  fi
  local guess
  for guess in \
    "$HOME/.local/share/mise/installs/github-ast-grep-ast-grep/"*/ast-grep \
    "/usr/local/bin/ast-grep"; do
    if [ -x "$guess" ]; then
      echo "$guess"
      return 0
    fi
  done
  return 1
}

# Resolve likec4 similarly. Used by tests that validate the projection
# output against the pinned likec4 CLI.
find_likec4() {
  if command -v likec4 >/dev/null 2>&1; then
    command -v likec4
    return 0
  fi
  local guess
  for guess in \
    "$HOME/.local/share/mise/installs/npm-likec4/"*/node_modules/.bin/likec4; do
    if [ -x "$guess" ]; then
      echo "$guess"
      return 0
    fi
  done
  return 1
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

# Runs run-manifest.sh inside the sandbox; extra args are forwarded.
run_manifest() {
  (
    cd "$SB" || exit 9
    XDG_CONFIG_HOME="$SB/config" XDG_DATA_HOME="$SB/data" \
      XDG_STATE_HOME="$SB/state" XDG_CACHE_HOME="$SB/cache" \
      ARCH_SKILLKIT_HOME="${SB_OVERRIDE:-}" \
      "$SCRIPTS/run-manifest.sh" "$@"
  )
}

# Runs scan-outline.sh inside the sandbox; extra args are forwarded.
run_scan() {
  local dir="$1"
  shift
  (
    cd "$dir" || exit 9
    XDG_CONFIG_HOME="$SB/config" XDG_DATA_HOME="$SB/data" \
      XDG_STATE_HOME="$SB/state" XDG_CACHE_HOME="$SB/cache" \
      ARCH_SKILLKIT_HOME="${SB_OVERRIDE:-}" \
      "$SCRIPTS/scan-outline.sh" "$@"
  )
}

# Runs scan-patterns.sh inside the sandbox; extra args are forwarded.
run_patterns() {
  local dir="$1"
  shift
  (
    cd "$dir" || exit 9
    XDG_CONFIG_HOME="$SB/config" XDG_DATA_HOME="$SB/data" \
      XDG_STATE_HOME="$SB/state" XDG_CACHE_HOME="$SB/cache" \
      ARCH_SKILLKIT_HOME="${SB_OVERRIDE:-}" \
      "$SCRIPTS/scan-patterns.sh" "$@"
  )
}

# Runs scan-build.sh inside the sandbox; extra args are forwarded.
run_build() {
  local dir="$1"
  shift
  (
    cd "$dir" || exit 9
    XDG_CONFIG_HOME="$SB/config" XDG_DATA_HOME="$SB/data" \
      XDG_STATE_HOME="$SB/state" XDG_CACHE_HOME="$SB/cache" \
      ARCH_SKILLKIT_HOME="${SB_OVERRIDE:-}" \
      "$SCRIPTS/scan-build.sh" "$@"
  )
}

# Runs scan.sh (the Scanner-role orchestrator) inside the sandbox.
run_scan_all() {
  local dir="$1"
  shift
  (
    cd "$dir" || exit 9
    XDG_CONFIG_HOME="$SB/config" XDG_DATA_HOME="$SB/data" \
      XDG_STATE_HOME="$SB/state" XDG_CACHE_HOME="$SB/cache" \
      ARCH_SKILLKIT_HOME="${SB_OVERRIDE:-}" \
      "$SCRIPTS/scan.sh" "$@"
  )
}

# Runs model-validate.sh inside the sandbox; extra args are forwarded.
run_model_validate() {
  local dir="$1"
  shift
  (
    cd "$dir" || exit 9
    XDG_CONFIG_HOME="$SB/config" XDG_DATA_HOME="$SB/data" \
      XDG_STATE_HOME="$SB/state" XDG_CACHE_HOME="$SB/cache" \
      ARCH_SKILLKIT_HOME="${SB_OVERRIDE:-}" \
      "$SCRIPTS/model-validate.sh" "$@"
  )
}

# Runs export-arrows.sh inside the sandbox; extra args are forwarded.
run_arrows() {
  local dir="$1"
  shift
  (
    cd "$dir" || exit 9
    XDG_CONFIG_HOME="$SB/config" XDG_DATA_HOME="$SB/data" \
      XDG_STATE_HOME="$SB/state" XDG_CACHE_HOME="$SB/cache" \
      ARCH_SKILLKIT_HOME="${SB_OVERRIDE:-}" \
      "$SCRIPTS/export-arrows.sh" "$@"
  )
}

# Runs report.sh inside the sandbox; extra args are forwarded.
run_report() {
  local dir="$1"
  shift
  (
    cd "$dir" || exit 9
    XDG_CONFIG_HOME="$SB/config" XDG_DATA_HOME="$SB/data" \
      XDG_STATE_HOME="$SB/state" XDG_CACHE_HOME="$SB/cache" \
      ARCH_SKILLKIT_HOME="${SB_OVERRIDE:-}" \
      "$SCRIPTS/report.sh" "$@"
  )
}

# Runs projects.sh inside the sandbox; extra args are forwarded.
run_projects() {
  (
    cd "$SB" || exit 9
    XDG_CONFIG_HOME="$SB/config" XDG_DATA_HOME="$SB/data" \
      XDG_STATE_HOME="$SB/state" XDG_CACHE_HOME="$SB/cache" \
      ARCH_SKILLKIT_HOME="${SB_OVERRIDE:-}" \
      "$SCRIPTS/projects.sh" "$@"
  )
}

# Runs the V2 Python facade (python -m archskillkit) inside the sandbox.
# ARCHSKILLKIT_PYTHON overrides the interpreter (dev venv, CI python).
ARCHSKILLKIT_PYTHON="${ARCHSKILLKIT_PYTHON:-python3}"
run_world() {
  (
    cd "$SB" || exit 9
    XDG_CONFIG_HOME="$SB/config" XDG_DATA_HOME="$SB/data" \
      XDG_STATE_HOME="$SB/state" XDG_CACHE_HOME="$SB/cache" \
      ARCH_SKILLKIT_HOME="${SB_OVERRIDE:-}" \
      "$ARCHSKILLKIT_PYTHON" -m archskillkit "$@"
  )
}

# Runs scan-build.sh with a PATH stripped of build tools (cargo/npm/gradle
# live in ~/.cargo/bin and asdf shims) while git/jq/mise remain available.
run_build_restricted() {
  local dir="$1"
  shift
  (
    cd "$dir" || exit 9
    XDG_CONFIG_HOME="$SB/config" XDG_DATA_HOME="$SB/data" \
      XDG_STATE_HOME="$SB/state" XDG_CACHE_HOME="$SB/cache" \
      ARCH_SKILLKIT_HOME="${SB_OVERRIDE:-}" \
      PATH="/usr/sbin:/usr/bin:/bin:$HOME/.local/bin" \
      "$SCRIPTS/scan-build.sh" "$@"
  )
}

# Runs doctor.sh inside the sandbox. $1: optional PATH for the child process
# (simulates missing dependencies deterministically). bash is resolved
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
  # RANDOM_GIT_COMMITTER_DISABLED=1: the dev machine's git wrapper refuses to
  # sign commits in remote-less (unclassified) repositories; stock git
  # installations ignore it.
  git init -q -b main "$1"
  printf 'fixture\n' >"$1/README.md"
  git -C "$1" add README.md
  RANDOM_GIT_COMMITTER_DISABLED=1 \
    git -C "$1" -c user.email=fixture@example.com -c user.name=fixture commit -qm "init"
  if [ -n "${2:-}" ]; then git -C "$1" remote add origin "$2"; fi
  return 0
}

# Creates a git repo from a repo fixture (fixtures/<name>) and registers it.
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

assert_eq() { # <desc> <expected> <actual>
  if [ "$2" = "$3" ]; then return 0; fi
  printf 'expected [%s], got [%s] (%s)\n' "$2" "$3" "$1" >&2
  return 1
}

assert_not_eq() { # <desc> <value-a> <value-b>
  if [ "$2" != "$3" ]; then return 0; fi
  printf 'both values are [%s] (%s)\n' "$2" "$1" >&2
  return 1
}

assert_file() { # <desc> <path>
  if [ -f "$2" ]; then return 0; fi
  printf 'missing file: %s (%s)\n' "$2" "$1" >&2
  return 1
}

assert_dir() { # <desc> <path>
  if [ -d "$2" ]; then return 0; fi
  printf 'missing dir: %s (%s)\n' "$2" "$1" >&2
  return 1
}

assert_rc() { # <desc> <expected-rc> <actual-rc>
  if [ "$3" -eq "$2" ]; then return 0; fi
  printf 'expected rc=%s, got rc=%s (%s)\n' "$2" "$3" "$1" >&2
  return 1
}

assert_output_contains() { # <desc> <needle> <haystack>
  case "$3" in
    *"$2"*) return 0 ;;
  esac
  printf 'output does not contain [%s]:\n%s\n' "$2" "$3" >&2
  return 1
}
