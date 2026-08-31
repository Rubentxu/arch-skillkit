#!/usr/bin/env bash
# Verify the environment ArchSkillKit needs (M1.2).
# Required today: git, jq, mise. Pipeline scanners are reported but only
# fail under --strict (they are needed from Phase 2 onwards).
# Read-only: doctor never creates workspaces or mutates the repository.
#
# Usage: doctor.sh [--strict]
set -euo pipefail
SCRIPT_DIR="${BASH_SOURCE[0]%/*}"
[ "$SCRIPT_DIR" = "${BASH_SOURCE[0]}" ] && SCRIPT_DIR=.
# shellcheck source=lib/common.sh
. "$SCRIPT_DIR/lib/common.sh"

strict=0
if [ "${1:-}" = "--strict" ]; then strict=1; fi

fail=0
skill_dir="$(cd "$SCRIPT_DIR/.." && pwd)"
runtime_dir="$skill_dir/runtime"

check_required() {
  local t
  printf 'required tools:\n'
  for t in git jq mise; do
    if command -v "$t" >/dev/null 2>&1; then
      printf '  [ok]      %-10s %s\n' "$t" "$(command -v "$t")"
    else
      printf '  [MISSING] %-10s required; install it (e.g. via your package manager or mise)\n' "$t"
      fail=1
    fi
  done
}

check_pipeline() {
  local t scanner_ok
  printf 'scanners:\n'

  # Required since M2.1/M2.2: on PATH or in the skill runtime.
  for t in ast-grep semgrep; do
    scanner_ok=0
    if command -v "$t" >/dev/null 2>&1; then
      printf '  [ok]      %-10s %s (PATH)\n' "$t" "$(command -v "$t")"
      scanner_ok=1
    elif arch_mise "$runtime_dir" "$t" --version >/dev/null 2>&1; then
      printf '  [ok]      %-10s %s (skill runtime)\n' "$t" "via mise"
      scanner_ok=1
    fi
    if [ "$scanner_ok" -eq 0 ]; then
      printf '  [MISSING] %-10s required; install with: mise install -C %s\n' "$t" "$runtime_dir"
      fail=1
    fi
  done

  printf 'upcoming scanners (not required yet):\n'
  if command -v likec4 >/dev/null 2>&1; then
    printf '  [ok]      %-10s %s\n' "likec4" "$(command -v likec4)"
  else
    printf '  [pending] %-10s lands with its own milestone (M4)\n' "likec4"
    if [ "$strict" -eq 1 ]; then fail=1; fi
  fi
}

show_optional_build_tools() {
  # Per-project tools (docs/06): their absence never fails the doctor; the
  # build metadata scan degrades to partial when a project needs them.
  local t
  printf 'optional build tools (per project):\n'
  for t in cargo npm gradle maven; do
    if command -v "$t" >/dev/null 2>&1; then
      printf '  [ok]      %-10s %s\n' "$t" "$(command -v "$t")"
    else
      printf '  [pending] %-10s needed only for repositories using that build system\n' "$t"
    fi
  done
}

show_roots() {
  local data_root
  data_root="$(arch_data_root)"
  printf 'resolved roots:\n'
  printf '  config: %s\n' "$(arch_config_root)"
  printf '  data:   %s\n' "$data_root"
  if [ -n "${ARCH_SKILLKIT_HOME:-}" ]; then
    printf '          (override active: ARCH_SKILLKIT_HOME=%s)\n' "$ARCH_SKILLKIT_HOME"
  fi
  printf '  state:  %s\n' "$(arch_state_root)"
  printf '  cache:  %s\n' "$(arch_cache_root)"

  printf 'permissions:\n'
  check_writable "data" "$data_root"
  check_writable "state" "$(arch_state_root)"
}

check_writable() {
  local label="$1" dir="$2"
  if [ ! -d "$dir" ]; then
    printf '  [pending] %-6s %s (created on first use)\n' "$label" "$dir"
  elif [ -w "$dir" ]; then
    printf '  [ok]      %-6s %s\n' "$label" "$dir"
  else
    printf '  [NO WRITE] %-6s %s\n' "$label" "$dir"
    fail=1
  fi
}

show_current_project() {
  local root pid
  root="$(repo_root "$PWD" 2>/dev/null || true)"
  if [ -z "$root" ]; then
    printf 'current directory: not inside a git repository\n'
    return 0
  fi
  printf 'current repository: %s\n' "$root"
  pid="$(registry_find_by_root "$root")"
  if [ -n "$pid" ]; then
    printf '  registered as: %s\n' "$pid"
    printf '  workspace:     %s\n' "$(registry_get_field "$pid" workspace)"
  else
    printf '  not registered yet (run workspace.sh to create its workspace)\n'
  fi
}

printf 'ArchSkillKit doctor\n'
check_required
check_pipeline
show_optional_build_tools
show_roots
show_current_project

if [ "$fail" -eq 1 ]; then
  printf 'doctor: FAILED — fix the items marked above and re-run.\n'
else
  printf 'doctor: OK\n'
fi
exit "$fail"
