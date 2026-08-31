#!/usr/bin/env bash
# Shared helpers for ArchSkillKit thin-glue scripts (ADR-0010).
# Path resolution, repository detection and registry IO only — no domain logic.

set -euo pipefail

ARCHSK_SCHEMA_VERSION=1

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
