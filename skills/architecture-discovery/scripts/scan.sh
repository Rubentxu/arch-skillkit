#!/usr/bin/env bash
# Scanner-role orchestration (M3.1, pipeline Fases 1-3 of docs/07).
# Selects the applicable deterministic scanners for the repository and runs
# them under ONE run manifest. Never interprets architecture; never writes
# into the source repository.
#
# Selection policy:
#   - ast-grep outline and Semgrep patterns: always applicable (they degrade
#     gracefully on unsupported languages);
#   - build metadata: only when a known build manifest is present.
#
# Usage: scan.sh [--repo <path>]
set -euo pipefail
SCRIPT_DIR="${BASH_SOURCE[0]%/*}"
[ "$SCRIPT_DIR" = "${BASH_SOURCE[0]}" ] && SCRIPT_DIR=.
# shellcheck source=lib/common.sh
. "$SCRIPT_DIR/lib/common.sh"

usage() {
  cat <<'EOF'
Usage: scan.sh [--repo <path>]

Runs all applicable deterministic scanners for the registered repository
under a single run manifest and prints the aggregate outcome.
EOF
}

repo_arg=""
while [ $# -gt 0 ]; do
  case "$1" in
    --repo)
      [ $# -ge 2 ] || { printf 'error: --repo needs a value\n' >&2; exit 2; }
      repo_arg="$2"
      shift 2
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      printf 'error: unknown option: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

require_tools git jq

root="$(repo_root "$repo_arg")" || {
  printf 'error: %s is not inside a git work tree\n' "${repo_arg:-$PWD}" >&2
  exit 1
}
pid="$(registry_find_by_root "$root")"
if [ -z "$pid" ]; then
  printf 'error: repository %s is not registered yet; run workspace.sh first\n' "$root" >&2
  exit 1
fi
workspace="$(registry_get_field "$pid" workspace)"

run_id="$("$SCRIPT_DIR/run-manifest.sh" start --repo "$root")"
statuses=()

# Runs one scanner under the orchestrator's run. A scanner failure never
# aborts the aggregation: it is recorded and the aggregate degrades.
run_scanner() {
  local script_name="$1" out st
  out="$("$SCRIPT_DIR/$script_name" --repo "$root" --run-id "$run_id" 2>&1)" || true
  printf '%s\n' "$out"
  st="$(printf '%s\n' "$out" | sed -n 's/^scan-[a-z]*: //p' | tail -n 1)"
  statuses+=("${st:-failed}")
  return 0
}

run_scanner "scan-outline.sh"
run_scanner "scan-patterns.sh"

if [ -f "$root/Cargo.toml" ] || [ -f "$root/package.json" ] ||
  [ -f "$root/build.gradle.kts" ] || [ -f "$root/build.gradle" ] ||
  [ -f "$root/pom.xml" ]; then
  run_scanner "scan-build.sh"
fi

aggregate() {
  local s success=0 partial=0 failed=0
  for s in "${statuses[@]:-}"; do
    case "$s" in
      success) success=$((success + 1)) ;;
      partial) partial=$((partial + 1)) ;;
      *) failed=$((failed + 1)) ;;
    esac
  done
  if [ "$failed" -gt 0 ] && [ "$success" -eq 0 ]; then
    printf 'failed\n'
  elif [ "$failed" -gt 0 ] || [ "$partial" -gt 0 ]; then
    printf 'partial\n'
  else
    printf 'success\n'
  fi
}

agg="$(aggregate)"
"$SCRIPT_DIR/run-manifest.sh" finish "$run_id" --status "$agg"

printf 'scan: %s\nrun_id: %s\nevidence: %s\n' "$agg" "$run_id" "$workspace/evidence/raw"
[ "$agg" != "failed" ]
