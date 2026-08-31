#!/usr/bin/env bash
# Project registry index: lists every registered project with its latest
# run outcome. Read-only.
#
# Usage: projects.sh
set -euo pipefail
SCRIPT_DIR="${BASH_SOURCE[0]%/*}"
[ "$SCRIPT_DIR" = "${BASH_SOURCE[0]}" ] && SCRIPT_DIR=.
# shellcheck source=lib/common.sh
. "$SCRIPT_DIR/lib/common.sh"

require_tools jq

registry="$(arch_registry_file)"
if [ ! -f "$registry" ]; then
  printf 'no projects registered yet (run workspace.sh inside a repository)\n'
  exit 0
fi

runs_root="$(arch_state_root)/runs"
printf '%-36s %-9s %-10s %s\n' "PROJECT" "STATUS" "SKILL" "ROOT"
jq -r '.projects[] | [.project_id, .root] | @tsv' "$registry" |
while IFS=$'\t' read -r pid root; do
  status="-"
  skill="-"
  latest="$(
    grep -l "\"project_id\": *\"$pid\"" "$runs_root"/*/manifest.json 2>/dev/null |
      sort | tail -n 1 || true
  )"
  if [ -n "$latest" ]; then
    status="$(jq -r '.status' "$latest")"
    skill="$(jq -r '.skill_version' "$latest")"
  fi
  printf '%-36s %-9s %-10s %s\n' "$pid" "$status" "$skill" "$root"
done
