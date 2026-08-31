#!/usr/bin/env bash
# Resolve or create the external workspace for a repository (M1.1).
# Repository detection, project identity, external XDG workspace, registry.
# The source repository is never written to (UAT-001).
#
# Usage: workspace.sh [--repo <path>] [--json] [--project-id <id>]
set -euo pipefail
SCRIPT_DIR="${BASH_SOURCE[0]%/*}"
[ "$SCRIPT_DIR" = "${BASH_SOURCE[0]}" ] && SCRIPT_DIR=.
# shellcheck source=lib/common.sh
. "$SCRIPT_DIR/lib/common.sh"

usage() {
  cat <<'EOF'
Usage: workspace.sh [--repo <path>] [--json] [--project-id <id>]

Resolves the external workspace for the git work tree containing <path>
(default: current directory), creating it and its registry entry when
needed. Prints a summary, or the project.json contents with --json.

Options:
  --repo <path>       repository directory (default: $PWD)
  --json              print project.json instead of a human summary
  --project-id <id>   explicit workspace identity for new projects
EOF
}

repo_arg=""
out="text"
forced_id=""
while [ $# -gt 0 ]; do
  case "$1" in
    --repo)
      [ $# -ge 2 ] || { printf 'error: --repo needs a value\n' >&2; exit 2; }
      repo_arg="$2"
      shift 2
      ;;
    --json)
      out="json"
      shift
      ;;
    --project-id)
      [ $# -ge 2 ] || { printf 'error: --project-id needs a value\n' >&2; exit 2; }
      forced_id="$2"
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
git -C "$root" rev-parse --verify HEAD >/dev/null 2>&1 || {
  printf 'error: repository at %s has no commits yet\n' "$root" >&2
  exit 1
}

remote="$(repo_remote "$root")"
branch="$(git -C "$root" rev-parse --abbrev-ref HEAD)"
commit="$(git -C "$root" rev-parse HEAD)"

status="created"
pid="$(registry_find_by_root "$root")"
if [ -n "$pid" ]; then
  status="existing"
elif [ -n "$remote" ]; then
  pid="$(registry_find_by_remote "$remote")"
  if [ -n "$pid" ]; then
    # Same remote, different checkout path: keep identity, record the move.
    status="moved"
    log_event "$pid" moved-repository "from=$(registry_get_field "$pid" root) to=$root"
  fi
fi
if [ -z "$pid" ]; then
  pid="${forced_id:-$(compute_project_id "$root" "$remote")}"
fi

workspace="$(arch_data_root)/projects/$pid"
create_workspace_dirs "$workspace"

jq -n \
  --argjson sv "$ARCHSK_SCHEMA_VERSION" \
  --arg pid "$pid" \
  --arg root "$root" \
  --arg remote "$remote" \
  --arg branch "$branch" \
  --arg commit "$commit" \
  --arg workspace "$workspace" \
  '{
    schema_version: $sv,
    project_id: $pid,
    root: $root,
    remote: (if $remote == "" then null else $remote end),
    branch: $branch,
    commit: $commit,
    workspace: $workspace
  }' >"$workspace/project.json"

registry_upsert "$(
  jq -n \
    --arg pid "$pid" \
    --arg root "$root" \
    --arg remote "$remote" \
    --arg workspace "$workspace" \
    --arg commit "$commit" \
    '{
      project_id: $pid,
      root: $root,
      remote: (if $remote == "" then null else $remote end),
      workspace: $workspace,
      last_commit: $commit
    }'
)"

if [ "$out" = "json" ]; then
  cat "$workspace/project.json"
else
  printf 'project_id: %s\n' "$pid"
  printf 'workspace:  %s\n' "$workspace"
  printf 'root:       %s\n' "$root"
  printf 'remote:     %s\n' "${remote:--}"
  printf 'branch:     %s\n' "$branch"
  printf 'commit:     %s\n' "$commit"
  printf 'registry:   %s\n' "$status"
fi
