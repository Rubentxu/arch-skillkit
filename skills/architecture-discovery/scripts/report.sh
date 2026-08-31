#!/usr/bin/env bash
# Organized report for a project (viewing layer).
# Generates reports/index.md: evidence summary, mermaid diagrams derived
# from the arrows-v1 views (render natively on GitHub/GitLab), model
# validation status and the commands to explore live. Read-only.
#
# Usage: report.sh [--repo <path>] [--serve]
set -euo pipefail
SCRIPT_DIR="${BASH_SOURCE[0]%/*}"
[ "$SCRIPT_DIR" = "${BASH_SOURCE[0]}" ] && SCRIPT_DIR=.
# shellcheck source=lib/common.sh
. "$SCRIPT_DIR/lib/common.sh"

usage() {
  cat <<'EOF'
Usage: report.sh [--repo <path>] [--serve]

Generates reports/index.md for the registered project. With --serve, starts
the likec4 live preview server for the model after generating the report.
EOF
}

repo_arg=""
serve=0
while [ $# -gt 0 ]; do
  case "$1" in
    --repo)
      [ $# -ge 2 ] || { printf 'error: --repo needs a value\n' >&2; exit 2; }
      repo_arg="$2"
      shift 2
      ;;
    --serve)
      serve=1
      shift
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
commit="$(jq -r .commit "$workspace/project.json")"
evidence="$workspace/evidence/raw"
arrows_dir="$workspace/arrows"
reports_dir="$workspace/reports"
model_dir="$workspace/likec4"
skill_dir="$(cd "$SCRIPT_DIR/.." && pwd)"
runtime_dir="$skill_dir/runtime"
skill_version="$(jq -r .skill_version "$skill_dir/version.json" 2>/dev/null || printf 'dev')"
now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
mkdir -p "$reports_dir"

index="$reports_dir/index.md"
{
  printf '# Architecture report — %s\n\n' "$pid"
  # shellcheck disable=SC2016  # backticks are markdown
printf -- '- commit: `%s`\n' "$commit"
  printf -- '- generated: %s (ArchSkillKit %s)\n' "$now" "$skill_version"
  # shellcheck disable=SC2016
printf -- '- evidence: `%s`\n\n' "$evidence"

  printf '## Evidence summary\n\n'
  printf '| scanner | findings |\n|---|---|\n'
  if [ -f "$evidence/ast-grep.jsonl" ]; then
    printf '| ast-grep outline | %s symbols |\n' "$(wc -l <"$evidence/ast-grep.jsonl" | tr -d ' ')"
  fi
  if [ -f "$evidence/semgrep.json" ]; then
    printf '| semgrep patterns | %s matches |\n' \
      "$(jq -r '.results | length' "$evidence/semgrep.json")"
  fi
  if [ -f "$evidence/build/build.provenance.json" ]; then
    printf '| build systems | %s |\n' \
      "$(jq -r '[.systems[].system] | join(", ")' "$evidence/build/build.provenance.json")"
  fi
  printf '\n'

  printf '## LikeC4 model\n\n'
  if find "$model_dir" -maxdepth 1 -name '*.c4' -type f 2>/dev/null | grep -q .; then
    if arch_mise "$runtime_dir" likec4 validate "$model_dir" >/dev/null 2>&1; then
      printf -- '- status: **valid** ✓\n'
    else
      printf -- '- status: **INVALID** — run scripts/model-validate.sh for details\n'
    fi
    # shellcheck disable=SC2016
printf -- '- live view: `mise exec -C %s -- likec4 serve %s`\n' "$runtime_dir" "$model_dir"
    # shellcheck disable=SC2016
printf -- '- static site: `mise exec -C %s -- likec4 build %s`\n' "$runtime_dir" "$model_dir"
  else
    printf -- '- no model yet (start from templates/model.c4 — references/likec4.md)\n'
  fi
  printf '\n'
} >"$index"

# Mermaid diagrams derived from the arrows-v1 views (render on GitHub).
mermaid_for() { # $1: .arrows file
  local nodes
  nodes="$(jq '.nodes | length' "$1")"
  if [ "$nodes" -gt 40 ]; then
    # shellcheck disable=SC2016
printf '```mermaid\nflowchart LR\n  n_summary["%s: %s nodes, %s relationships (too many to render)"]\n```\n' \
      "$(jq -r .title "$1")" "$nodes" "$(jq '.relationships | length' "$1")"
    return 0
  fi
  jq -r '{
    nodes: [.nodes[] | {
      mid: ("n_" + (.id | gsub("[^a-zA-Z0-9_]"; "_"))),
      label: ((.properties.name // .properties.location // .id) | gsub("\""; "'\''"))
    }],
    rels: [.relationships[] | {
      a: ("n_" + (.start | gsub("[^a-zA-Z0-9_]"; "_"))),
      b: ("n_" + (.end | gsub("[^a-zA-Z0-9_]"; "_"))),
      t: .type
    }]
  } | "```mermaid\nflowchart LR\n" +
      ([.nodes[] | "  " + .mid + "[\"" + .label + "\"]"] | join("\n")) + "\n" +
      ([.rels[] | "  " + .a + " -->|" + .t + "| " + .b] | join("\n")) + "\n```"' "$1"
}

printf '## Diagrams (Arrows views)\n\n' >>"$index"
diagrams=0
for f in "$arrows_dir"/*.arrows; do
  [ -f "$f" ] || break
  title="$(jq -r .title "$f")"
  # shellcheck disable=SC2129
  printf '### %s\n\n' "$title" >>"$index"
  printf '%s nodes, %s relationships\n\n' "$(jq '.nodes | length' "$f")" "$(jq '.relationships | length' "$f")" >>"$index"
  mermaid_for "$f" >>"$index"
  printf '\n' >>"$index"
  diagrams=$((diagrams + 1))
done
if [ "$diagrams" -eq 0 ]; then
  printf 'No arrows views yet — run scripts/export-arrows.sh after a scan.\n\n' >>"$index"
fi

{
  printf '## Handoff reports\n\n'
  for r in inventory.md review-findings.md validation-report.md; do
    [ -f "$reports_dir/$r" ] && printf -- '- [%s](%s)\n' "$r" "$r"
  done
  # shellcheck disable=SC2016
printf '\n- Full model source: `%s`\n' "$model_dir"
} >>"$index"

printf 'report: %s\n' "$index"

if [ "$serve" -eq 1 ]; then
  if find "$model_dir" -maxdepth 1 -name '*.c4' -type f 2>/dev/null | grep -q .; then
    arch_mise "$runtime_dir" likec4 serve "$model_dir"
  else
    printf 'error: --serve needs a model (likec4/*.c4)\n' >&2
    exit 1
  fi
fi
