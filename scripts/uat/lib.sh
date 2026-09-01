#!/usr/bin/env bash

# Shared safety/configuration helpers for the local UAT runner.

uat_die() {
  printf 'error: %s\n' "$*" >&2
  return 1
}

uat_require_tools() {
  local tool missing=0
  for tool in "$@"; do
    if ! command -v "$tool" >/dev/null 2>&1; then
      printf 'error: required tool not found: %s\n' "$tool" >&2
      missing=1
    fi
  done
  return "$missing"
}

uat_disable_runtime_downloads() {
  export MISE_AUTO_INSTALL=0
  printf '%s\n' "$MISE_AUTO_INSTALL"
}

uat_validate_id() {
  case "${1:-}" in
    '' | *[!a-zA-Z0-9._-]*)
      uat_die "invalid target id: ${1:-<empty>}"
      ;;
  esac
}

uat_resolve_target() {
  local root="$1" target="$2" config
  uat_validate_id "$target" || return 1
  config="$root/tests/uat/targets/$target.json"
  [ -f "$config" ] || {
    uat_die "unknown UAT target '$target'"
    return 1
  }
  jq -e \
    --arg id "$target" \
    '.schema_version == 1
      and .id == $id
      and (.repository | type == "string" and length > 0)
      and (.normalized_remote | type == "string" and length > 0)
      and (.commit | type == "string" and test("^[0-9a-f]{40}$"))
      and (.local_candidates | type == "array")' \
    "$config" >/dev/null || {
      uat_die "invalid target configuration: $config"
      return 1
    }
  printf '%s\n' "$config"
}

uat_assert_safe_child() {
  local parent="$1" child="$2" normalized_parent normalized_child
  [ -n "$parent" ] && [ -n "$child" ] || {
    uat_die "cleanup paths must not be empty"
    return 1
  }
  normalized_parent="$(realpath -m -- "$parent")"
  normalized_child="$(realpath -m -- "$child")"
  [ "$normalized_parent" != / ] || {
    uat_die "refusing cleanup under filesystem root"
    return 1
  }
  [ "$normalized_child" != "$normalized_parent" ] || {
    uat_die "refusing to remove cleanup root itself"
    return 1
  }
  case "$normalized_child" in
    "$normalized_parent"/*) ;;
    *)
      uat_die "refusing cleanup outside $normalized_parent: $normalized_child"
      return 1
      ;;
  esac
}

uat_safe_remove_dir() {
  local parent="$1" child="$2"
  uat_assert_safe_child "$parent" "$child" || return 1
  [ ! -e "$child" ] && return 0
  [ ! -L "$child" ] || {
    uat_die "refusing to recursively remove symlink: $child"
    return 1
  }
  chmod -R u+w -- "$child" 2>/dev/null || true
  rm -rf -- "$child"
}

uat_assert_worktree() {
  local repo="$1" inside bare
  inside="$(git -C "$repo" rev-parse --is-inside-work-tree 2>/dev/null || true)"
  bare="$(git -C "$repo" rev-parse --is-bare-repository 2>/dev/null || true)"
  if [ "$inside" != true ] || [ "$bare" = true ]; then
    uat_die "source override must be a non-bare Git worktree: $repo"
    return 1
  fi
}

uat_scan_succeeded() {
  local output="$1"
  printf '%s\n' "$output" | grep -Fxq 'scan: success'
}

uat_untracked_fingerprint() {
  local repo="$1"
  (
    cd "$repo" || exit 1
    while IFS= read -r -d '' path; do
      printf '%s\0' "$path"
      if [ -L "$path" ]; then
        printf 'symlink\0%s\0' "$(readlink -- "$path")"
      elif [ -f "$path" ]; then
        printf 'file\0%s\0' "$(sha256sum -- "$path" | cut -d' ' -f1)"
      else
        printf 'special\0\0'
      fi
    done < <(git ls-files --others --exclude-standard -z)
  ) | sha256sum | cut -d' ' -f1
}

uat_git_evidence() {
  local repo="$1" status diff_hash remote untracked_hash
  status="$(git -C "$repo" status --porcelain=v1 --untracked-files=all)"
  diff_hash="$(git -C "$repo" diff --no-ext-diff --binary HEAD | sha256sum | cut -d' ' -f1)"
  untracked_hash="$(uat_untracked_fingerprint "$repo")" || return 1
  remote="$(git -C "$repo" remote get-url origin 2>/dev/null || true)"
  jq -n \
    --arg repo "$(realpath "$repo")" \
    --arg head "$(git -C "$repo" rev-parse HEAD)" \
    --arg status "$status" \
    --arg diff_sha256 "$diff_hash" \
    --arg untracked_sha256 "$untracked_hash" \
    --arg remote "$remote" \
    '{repo: $repo, head: $head, status_porcelain: $status,
      diff_sha256: $diff_sha256, untracked_sha256: $untracked_sha256,
      remote: $remote}'
}

uat_same_git_evidence() {
  local before="$1" after="$2"
  jq -e --slurp '.[0] == .[1]' "$before" "$after" >/dev/null
}
