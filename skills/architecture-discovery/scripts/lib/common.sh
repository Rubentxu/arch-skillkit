#!/usr/bin/env bash
# Shared helpers for ArchSkillKit thin-glue scripts (ADR-0010).
# Path resolution, repository detection and registry IO only — no domain logic.

set -euo pipefail

ARCHSK_SCHEMA_VERSION=1

# Resource policy for deterministic scanners. Defaults deliberately favor
# resource-constrained machines; callers may raise them with positive integer
# environment overrides. Keep the Node heap flag constructed in one place so
# a caller's NODE_OPTIONS never accumulates duplicate max-old-space-size flags.
arch_positive_integer() {
  local name="$1" value="$2"
  case "$value" in
    '' | *[!0-9]* | 0 | 0*)
      printf 'error: %s must be a positive integer; got %s\n' "$name" "${value:-<empty>}" >&2
      return 2
      ;;
  esac
}

arch_ast_grep_threads() {
  local value="${ARCHSK_AST_GREP_THREADS:-1}"
  arch_positive_integer ARCHSK_AST_GREP_THREADS "$value" || return
  printf '%s\n' "$value"
}

arch_semgrep_jobs() {
  local value="${ARCHSK_SEMGREP_JOBS:-1}"
  arch_positive_integer ARCHSK_SEMGREP_JOBS "$value" || return
  printf '%s\n' "$value"
}

arch_node_max_old_space_size_mb() {
  local value="${ARCHSK_NODE_MAX_OLD_SPACE_SIZE_MB:-512}"
  arch_positive_integer ARCHSK_NODE_MAX_OLD_SPACE_SIZE_MB "$value" || return
  printf '%s\n' "$value"
}

arch_node_options_with_heap() {
  local heap_mb="$1" inherited="${NODE_OPTIONS:-}" cleaned
  arch_positive_integer ARCHSK_NODE_MAX_OLD_SPACE_SIZE_MB "$heap_mb" || return
  # Node parses NODE_OPTIONS as whitespace-separated flags. Remove both the
  # hyphenated and underscored spellings, whether their value is joined with
  # '=' or supplied as the next token, before adding one canonical flag.
  cleaned="$(printf '%s\n' "$inherited" | sed -E 's/(^|[[:space:]])--max[-_]old[-_]space[-_]size(=[^[:space:]]+|[[:space:]]+[^[:space:]]+)//g; s/^[[:space:]]+//; s/[[:space:]]+$//; s/[[:space:]]+/ /g')"
  if [ -n "$cleaned" ]; then
    printf '%s --max-old-space-size=%s\n' "$cleaned" "$heap_mb"
  else
    printf '%s\n' "--max-old-space-size=$heap_mb"
  fi
}

arch_config_root() {
  printf '%s\n' "${XDG_CONFIG_HOME:-$HOME/.config}/arch-skillkit"
}

# The data root honors the explicit workspace-root override documented in
# docs/04-workspace-layout.md (ARCH_SKILLKIT_HOME).
arch_data_root() {
  if [ -n "${ARCH_SKILLKIT_HOME:-}" ]; then
    printf '%s\n' "$ARCH_SKILLKIT_HOME"
  else
    printf '%s\n' "${XDG_DATA_HOME:-$HOME/.local/share}/arch-skillkit"
  fi
}

arch_state_root() {
  printf '%s\n' "${XDG_STATE_HOME:-$HOME/.local/state}/arch-skillkit"
}

arch_cache_root() {
  printf '%s\n' "${XDG_CACHE_HOME:-$HOME/.cache}/arch-skillkit"
}

arch_registry_file() {
  printf '%s\n' "$(arch_state_root)/registry.json"
}

arch_mise() {
  # Runs a tool from the skill runtime through mise, isolated from the
  # surrounding environment:
  # - XDG_* are dropped: mise 2026 gives XDG_DATA_HOME precedence over
  #   MISE_DATA_HOME, so a sandboxed XDG (tests, CI) would make mise believe
  #   nothing is installed and re-download the world;
  # - MISE_CONFIG_DIR points at an empty config dir so the user's global
  #   config (~/.tool-versions, ~/.config/mise) is not merged into resolution.
  # $1: runtime dir with mise.toml; rest: command and args.
  local runtime_dir="$1"
  shift
  local cfg_dir semgrep_dir node_heap node_options
  cfg_dir="$(arch_cache_root)/mise-config"
  semgrep_dir="$(arch_cache_root)/semgrep"
  mkdir -p "$cfg_dir" "$semgrep_dir"
  # An empty, fresh version response keeps offline/test runs deterministic;
  # Semgrep refreshes it normally after the cache timestamp expires.
  if [ ! -f "$semgrep_dir/version" ]; then
    printf '%s\n{}\n' "$(date +%s)" >"$semgrep_dir/version"
  fi
  node_heap="$(arch_node_max_old_space_size_mb)" || return
  node_options="$(arch_node_options_with_heap "$node_heap")" || return
  env -u XDG_DATA_HOME -u XDG_CACHE_HOME -u XDG_CONFIG_HOME \
    MISE_CONFIG_DIR="$cfg_dir" \
    SEMGREP_SETTINGS_FILE="${SEMGREP_SETTINGS_FILE:-$semgrep_dir/settings.yml}" \
    SEMGREP_VERSION_CACHE_PATH="${SEMGREP_VERSION_CACHE_PATH:-$semgrep_dir/version}" \
    SEMGREP_LOG_FILE="${SEMGREP_LOG_FILE:-$semgrep_dir/semgrep.log}" \
    NODE_OPTIONS="$node_options" \
    mise exec -C "$runtime_dir" -- "$@"
}

require_tools() {
  local t missing=0
  for t in "$@"; do
    if ! command -v "$t" >/dev/null 2>&1; then
      printf 'error: required tool not found: %s\n' "$t" >&2
      missing=1
    fi
  done
  return "$missing"
}

repo_root() {
  # Canonical root of the git work tree containing $1 (default: $PWD).
  local dir="${1:-$PWD}" root
  root="$(git -C "$dir" rev-parse --show-toplevel 2>/dev/null)" || return 1
  realpath "$root"
}

repo_remote() {
  # Normalized origin (or first) remote URL; empty output when none exists.
  local root="$1" url="" first
  url="$(git -C "$root" config --get remote.origin.url 2>/dev/null || true)"
  if [ -z "$url" ]; then
    first="$(git -C "$root" remote 2>/dev/null | head -n 1)"
    if [ -n "$first" ]; then
      url="$(git -C "$root" config --get "remote.${first}.url" 2>/dev/null || true)"
    fi
  fi
  [ -n "$url" ] || return 0
  normalize_remote "$url"
}

normalize_remote() {
  # Enough identity to compare across machines and protocols:
  # git@gitlab.com:grp/repo.git, https://user@host/grp/repo.git and
  # ssh://git@host:2222/grp/repo.git all become host/grp/repo.
  local url="$1"
  case "$url" in
    ssh://*)
      url="${url#ssh://}"
      url="${url#git@}"
      url="$(printf '%s' "$url" | sed -E 's#^([^/:]+):[0-9]+/#\1/#')"
      ;;
    git@*)
      url="${url#git@}"
      url="$(printf '%s' "$url" | sed -E 's#^([^/:]+):/#\1/#')"
      ;;
    git://*)
      url="${url#git://}"
      ;;
    http://* | https://*)
      url="${url#http://}"
      url="${url#https://}"
      url="${url#*@}"
      ;;
  esac
  url="${url%.git}"
  url="${url%/}"
  printf '%s\n' "$url"
}

project_name() {
  # Repository basename sanitized for use inside a project id.
  local name
  name="$(basename "$1")"
  printf '%s' "$name" | tr -c '[:alnum:]._-' '-' | sed -E 's/-+/-/g; s/^-+//; s/-+$//'
}

compute_project_id() {
  # <repo-name>-<short-hash>. Hash seed precedence per docs/04: normalized
  # remote when present, canonical checkout path otherwise.
  local root="$1" remote="$2" seed hash
  if [ -n "$remote" ]; then seed="$remote"; else seed="$root"; fi
  hash="$(printf '%s' "$seed" | sha256sum | cut -c1-8)"
  printf '%s-%s\n' "$(project_name "$root")" "$hash"
}

registry_init() {
  local reg
  reg="$(arch_registry_file)"
  mkdir -p "$(dirname "$reg")"
  [ -f "$reg" ] ||
    printf '{"schema_version":%s,"projects":[]}\n' "$ARCHSK_SCHEMA_VERSION" >"$reg"
}

registry_find_by_root() {
  local root="$1" reg id
  reg="$(arch_registry_file)"
  [ -f "$reg" ] || return 0
  id="$(jq -r --arg root "$root" '.projects[]? | select(.root == $root) | .project_id' "$reg" 2>/dev/null | head -n 1)"
  [ -n "$id" ] && printf '%s\n' "$id"
  return 0
}

registry_find_by_remote() {
  local remote="$1" reg id
  reg="$(arch_registry_file)"
  [ -f "$reg" ] || return 0
  id="$(jq -r --arg remote "$remote" '.projects[]? | select(.remote == $remote) | .project_id' "$reg" 2>/dev/null | head -n 1)"
  [ -n "$id" ] && printf '%s\n' "$id"
  return 0
}

registry_get_field() {
  local pid="$1" field="$2" reg
  reg="$(arch_registry_file)"
  [ -f "$reg" ] || return 0
  jq -r --arg pid "$pid" --arg f "$field" '.projects[]? | select(.project_id == $pid) | .[$f]' "$reg" 2>/dev/null | head -n 1
  return 0
}

registry_upsert() {
  # $1: full project record JSON. Writes atomically; preserves created_at.
  local rec="$1" reg pid now created tmp
  reg="$(arch_registry_file)"
  registry_init
  pid="$(printf '%s' "$rec" | jq -r '.project_id')"
  now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  created="$(registry_get_field "$pid" created_at)"
  [ -n "$created" ] || created="$now"
  rec="$(printf '%s' "$rec" | jq --arg created "$created" --arg updated "$now" '. + {created_at: $created, updated_at: $updated}')"
  tmp="$(mktemp "$(dirname "$reg")/.registry.XXXXXX")"
  jq --arg pid "$pid" --argjson rec "$rec" '
    .schema_version = 1
    | .projects = ((.projects // []) | map(select(.project_id != $pid)) + [$rec])
  ' "$reg" >"$tmp"
  mv "$tmp" "$reg"
}

log_event() {
  # $1: project_id, $2: event name, $3: optional detail.
  local f
  f="$(arch_state_root)/events.log"
  mkdir -p "$(dirname "$f")"
  printf '%s project=%s event=%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$2" "${3:-}" >>"$f"
}

create_workspace_dirs() {
  # Layout contract from docs/04-workspace-layout.md.
  local ws="$1"
  mkdir -p "$ws/evidence/raw" "$ws/evidence/curated" "$ws/evidence/provenance"
  mkdir -p "$ws/knowledge" "$ws/likec4/views" "$ws/arrows" "$ws/reports" "$ws/exports"
  mkdir -p "$(arch_data_root)/templates"
}
