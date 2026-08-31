#!/usr/bin/env bash
# Architectural pattern scan (M2.2, pipeline Fase 2 of docs/07).
# Runs the pinned Semgrep with the skill rule pack (high-confidence
# framework markers) over the repository and stores the raw JSON as
# evidence — no LLM involved. The repository is never written to.
#
# Usage: scan-patterns.sh [--repo <path>]
set -euo pipefail
SCRIPT_DIR="${BASH_SOURCE[0]%/*}"
[ "$SCRIPT_DIR" = "${BASH_SOURCE[0]}" ] && SCRIPT_DIR=.
# shellcheck source=lib/common.sh
. "$SCRIPT_DIR/lib/common.sh"

usage() {
  cat <<'EOF'
Usage: scan-patterns.sh [--repo <path>]

Runs the Semgrep architecture rule pack over the registered repository and
writes evidence/raw/semgrep.json plus provenance to the project workspace.
Opens and closes its own run manifest entry.
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
rules_dir="$skill_dir/rules/semgrep"
evidence_dir="$workspace/evidence/raw"

run_id="$("$SCRIPT_DIR/run-manifest.sh" start --repo "$root")"
commit="$(git -C "$root" rev-parse HEAD)"

semgrep() {
  arch_mise "$runtime_dir" semgrep "$@"
}

tmp_evidence="$evidence_dir/.semgrep.json.tmp"
if semgrep scan --config "$rules_dir" --json --metrics=off --quiet \
    --no-rewrite-rule-ids "$root" >"$tmp_evidence" 2>"$evidence_dir/semgrep.stderr.log"; then
  mv "$tmp_evidence" "$evidence_dir/semgrep.json"
  scan_status="success"
else
  mv "$tmp_evidence" "$evidence_dir/semgrep.json" 2>/dev/null || true
  printf 'error: semgrep scan failed; see %s\n' "$evidence_dir/semgrep.stderr.log" >&2
  "$SCRIPT_DIR/run-manifest.sh" finish "$run_id" --status failed
  exit 1
fi

tool_version="$(semgrep --version 2>/dev/null || printf 'absent')"
rules_checksum="$(find "$rules_dir" -name '*.yml' -type f -print0 |
  sort -z | xargs -0 cat | sha256sum | cut -d' ' -f1)"

jq -n \
  --argjson sv 1 \
  --arg tool "semgrep" \
  --arg tool_version "$tool_version" \
  --arg rules_checksum "$rules_checksum" \
  --arg command "semgrep scan --config rules/semgrep --json --metrics=off --no-rewrite-rule-ids $root" \
  --arg commit "$commit" \
  --arg run_id "$run_id" \
  --arg recorded_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --arg note "results[].extra.lines is gated by semgrep OSS (prints 'requires login'); use path and range instead" \
  '{
    schema_version: $sv,
    tool: $tool,
    tool_version: $tool_version,
    rules_checksum: $rules_checksum,
    command: $command,
    commit: $commit,
    run_id: $run_id,
    recorded_at: $recorded_at,
    note: $note
  }' >"$evidence_dir/semgrep.provenance.json"

"$SCRIPT_DIR/run-manifest.sh" record "$run_id" \
  --scanner semgrep-architecture \
  --tool "semgrep=$tool_version"

n_results="$(jq -r '.results | length' "$evidence_dir/semgrep.json" 2>/dev/null || printf '0')"
if [ "$n_results" = "0" ]; then
  printf 'warning: no architectural patterns matched for %s (no supported frameworks?)\n' "$root" >&2
fi

"$SCRIPT_DIR/run-manifest.sh" finish "$run_id" --status "$scan_status"
printf 'scan-patterns: %s\nrun_id: %s\nevidence: %s\nmatches: %s\n' \
  "$scan_status" "$run_id" "$evidence_dir/semgrep.json" "$n_results"
