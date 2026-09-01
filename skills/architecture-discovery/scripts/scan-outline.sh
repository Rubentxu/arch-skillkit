#!/usr/bin/env bash
# Deterministic structural outline scan (M2.1, pipeline Fase 1 of docs/07).
# Runs the pinned ast-grep with the skill rule pack against the repository
# and stores the raw NDJSON as evidence — no LLM involved. The repository is
# never written to; all output lands in the project workspace.
#
# Usage: scan-outline.sh [--repo <path>]
set -euo pipefail
SCRIPT_DIR="${BASH_SOURCE[0]%/*}"
[ "$SCRIPT_DIR" = "${BASH_SOURCE[0]}" ] && SCRIPT_DIR=.
# shellcheck source=lib/common.sh
. "$SCRIPT_DIR/lib/common.sh"

usage() {
  cat <<'EOF'
Usage: scan-outline.sh [--repo <path>] [--run-id <id>]

Runs the ast-grep structural outline over the registered repository and
writes evidence/raw/ast-grep.jsonl plus provenance to the project workspace.
Opens and closes its own run manifest entry.
EOF
}

repo_arg=""
run_id_arg=""
while [ $# -gt 0 ]; do
  case "$1" in
    --repo)
      [ $# -ge 2 ] || { printf 'error: --repo needs a value\n' >&2; exit 2; }
      repo_arg="$2"
      shift 2
      ;;
    --run-id)
      [ $# -ge 2 ] || { printf 'error: --run-id needs a value\n' >&2; exit 2; }
      run_id_arg="$2"
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

require_tools git jq mise

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

skill_dir="$(cd "$SCRIPT_DIR/.." && pwd)"
runtime_dir="$skill_dir/runtime"
rules_dir="$skill_dir/rules/ast-grep"
evidence_dir="$workspace/evidence/raw"
astgrep_threads="$(arch_ast_grep_threads)" || exit $?

if [ -n "$run_id_arg" ]; then
  # Orchestrated mode: the caller owns the run manifest lifecycle.
  run_id="$run_id_arg"
else
  run_id="$("$SCRIPT_DIR/run-manifest.sh" start --repo "$root")"
fi
commit="$(git -C "$root" rev-parse HEAD)"

ast_grep() {
  arch_mise "$runtime_dir" ast-grep "$@"
}

tmp_evidence="$evidence_dir/.ast-grep.jsonl.tmp"
if ast_grep scan -c "$rules_dir/sgconfig.yml" --threads "$astgrep_threads" --json=stream "$root" >"$tmp_evidence" 2>"$evidence_dir/ast-grep.stderr.log"; then
  mv "$tmp_evidence" "$evidence_dir/ast-grep.jsonl"
  scan_status="success"
else
  mv "$tmp_evidence" "$evidence_dir/ast-grep.jsonl" 2>/dev/null || true
  printf 'error: ast-grep scan failed; see %s\n' "$evidence_dir/ast-grep.stderr.log" >&2
  if [ -z "$run_id_arg" ]; then
    "$SCRIPT_DIR/run-manifest.sh" finish "$run_id" --status failed
  fi
  exit 1
fi

tool_version="$(ast_grep --version 2>/dev/null || printf 'absent')"
rules_checksum="$(find "$rules_dir" -name '*.yml' -type f -print0 |
  sort -z | xargs -0 cat | sha256sum | cut -d' ' -f1)"

jq -n \
  --argjson sv 1 \
  --arg tool "ast-grep" \
  --arg tool_version "$tool_version" \
  --arg rules_checksum "$rules_checksum" \
  --arg command "ast-grep scan -c sgconfig.yml --threads $astgrep_threads --json=stream $root" \
  --argjson threads "$astgrep_threads" \
  --arg commit "$commit" \
  --arg run_id "$run_id" \
  --arg recorded_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  '{
    schema_version: $sv,
    tool: $tool,
    tool_version: $tool_version,
    rules_checksum: $rules_checksum,
    command: $command,
    resource_limits: {threads: $threads},
    commit: $commit,
    run_id: $run_id,
    recorded_at: $recorded_at
  }' >"$evidence_dir/ast-grep.provenance.json"

"$SCRIPT_DIR/run-manifest.sh" record "$run_id" \
  --scanner ast-grep-outline \
  --tool "ast_grep=$tool_version"

if [ ! -s "$evidence_dir/ast-grep.jsonl" ]; then
  printf 'warning: no structural outline matches for %s (no supported sources?)\n' "$root" >&2
fi

if [ -z "$run_id_arg" ]; then
  "$SCRIPT_DIR/run-manifest.sh" finish "$run_id" --status "$scan_status"
fi
printf 'scan-outline: %s\nrun_id: %s\nevidence: %s\n' "$scan_status" "$run_id" "$evidence_dir/ast-grep.jsonl"
