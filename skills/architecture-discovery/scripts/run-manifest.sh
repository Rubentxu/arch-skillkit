#!/usr/bin/env bash
# Run manifest lifecycle (docs/15): what ran, with which versions, against
# which commit, and with which outcome. State-only: manifests live under
# $XDG_STATE_HOME/arch-skillkit/runs/<run_id>/manifest.json.
#
# Usage: run-manifest.sh start [--repo <path>]
#        run-manifest.sh finish <run_id> --status <success|partial|failed>
#        run-manifest.sh record <run_id> [--scanner <name>] [--tool <key>=<version>]
set -euo pipefail
SCRIPT_DIR="${BASH_SOURCE[0]%/*}"
[ "$SCRIPT_DIR" = "${BASH_SOURCE[0]}" ] && SCRIPT_DIR=.
# shellcheck source=lib/common.sh
. "$SCRIPT_DIR/lib/common.sh"

usage() {
  cat <<'EOF'
Usage: run-manifest.sh start [--repo <path>]

Starts a run for a registered project (run workspace.sh first) and prints
the new run id on stdout.
EOF
}

require_tools git jq

cmd="${1:-}"
[ -n "$cmd" ] || { usage >&2; exit 2; }
shift

case "$cmd" in
  start)
    repo_arg=""
    while [ $# -gt 0 ]; do
      case "$1" in
        --repo)
          [ $# -ge 2 ] || { printf 'error: --repo needs a value\n' >&2; exit 2; }
          repo_arg="$2"
          shift 2
          ;;
        *)
          printf 'error: unknown option: %s\n' "$1" >&2
          usage >&2
          exit 2
          ;;
      esac
    done

    root="$(repo_root "$repo_arg")" || {
      printf 'error: %s is not inside a git work tree\n' "${repo_arg:-$PWD}" >&2
      exit 1
    }
    pid="$(registry_find_by_root "$root")"
    if [ -z "$pid" ]; then
      printf 'error: repository %s is not registered yet; run workspace.sh first\n' "$root" >&2
      exit 1
    fi

    run_id="$(date -u +%Y%m%dT%H%M%SZ)-$$"
    manifest_dir="$(arch_state_root)/runs/$run_id"
    mkdir -p "$manifest_dir"

    # Skill version contract (docs/10): declared in version.json, overridable
    # via ARCH_SKILLKIT_SKILL_VERSION; fallback for development checkouts.
    skill_version="${ARCH_SKILLKIT_SKILL_VERSION:-}"
    if [ -z "$skill_version" ]; then
      version_file="$(cd "$SCRIPT_DIR/.." && pwd)/version.json"
      if [ -f "$version_file" ]; then
        skill_version="$(jq -r .skill_version "$version_file")"
      fi
    fi
    skill_version="${skill_version:-0.0.0-dev}"

    tool_version() { # <cmd...>
      if command -v "$1" >/dev/null 2>&1; then
        "$@" 2>/dev/null | head -n 1
      else
        printf 'absent'
      fi
    }

    jq -n \
      --argjson sv 1 \
      --arg run_id "$run_id" \
      --arg pid "$pid" \
      --arg commit "$(git -C "$root" rev-parse HEAD)" \
      --arg skill_version "$skill_version" \
      --arg started_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
      --arg git_v "$(tool_version git --version)" \
      --arg jq_v "$(tool_version jq --version)" \
      --arg mise_v "$(tool_version mise --version)" \
      '{
        schema_version: $sv,
        run_id: $run_id,
        project_id: $pid,
        commit: $commit,
        skill_version: $skill_version,
        status: "running",
        started_at: $started_at,
        ended_at: null,
        tools: {git: $git_v, jq: $jq_v, mise: $mise_v},
        scanners: [],
        warnings: [],
        errors: []
      }' >"$manifest_dir/manifest.json"

    printf '%s\n' "$run_id"
    ;;
  finish)
    run_id="${1:-}"
    shift || true
    status_value=""
    while [ $# -gt 0 ]; do
      case "$1" in
        --status)
          [ $# -ge 2 ] || { printf 'error: --status needs a value\n' >&2; exit 2; }
          status_value="$2"
          shift 2
          ;;
        *)
          printf 'error: unknown option: %s\n' "$1" >&2
          usage >&2
          exit 2
          ;;
      esac
    done

    manifest="$(arch_state_root)/runs/$run_id/manifest.json"
    if [ ! -f "$manifest" ]; then
      printf 'error: unknown run id: %s\n' "$run_id" >&2
      exit 1
    fi

    case "$status_value" in
      success | partial | failed) ;;
      *)
        printf 'error: invalid status: %s (expected success, partial or failed)\n' "$status_value" >&2
        exit 2
        ;;
    esac

    current="$(jq -r .status "$manifest")"
    if [ "$current" != "running" ]; then
      printf 'error: run %s is already finished (status: %s)\n' "$run_id" "$current" >&2
      exit 1
    fi

    tmp="$(mktemp "$(dirname "$manifest")/.manifest.XXXXXX")"
    jq --arg status "$status_value" --arg ended_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
      '.status = $status | .ended_at = $ended_at' "$manifest" >"$tmp"
    mv "$tmp" "$manifest"
    ;;
  record)
    run_id="${1:-}"
    shift || true
    [ -n "$run_id" ] || { usage >&2; exit 2; }
    scanners=()
    tools=()
    while [ $# -gt 0 ]; do
      case "$1" in
        --scanner)
          [ $# -ge 2 ] || { printf 'error: --scanner needs a value\n' >&2; exit 2; }
          scanners+=("$2")
          shift 2
          ;;
        --tool)
          [ $# -ge 2 ] || { printf 'error: --tool needs a value\n' >&2; exit 2; }
          tools+=("$2")
          shift 2
          ;;
        *)
          printf 'error: unknown option: %s\n' "$1" >&2
          usage >&2
          exit 2
          ;;
      esac
    done

    manifest="$(arch_state_root)/runs/$run_id/manifest.json"
    if [ ! -f "$manifest" ]; then
      printf 'error: unknown run id: %s\n' "$run_id" >&2
      exit 1
    fi

    jq_args=()
    jq_filter="."
    for s in "${scanners[@]:-}"; do
      [ -n "$s" ] || continue
      jq_args+=(--arg s "$s")
      jq_filter="$jq_filter | .scanners = (if (.scanners | index(\$s)) then .scanners else .scanners + [\$s] end)"
    done
    for t in "${tools[@]:-}"; do
      [ -n "$t" ] || continue
      case "$t" in
        *=*) ;;
        *) printf 'error: invalid --tool: %s (expected key=version)\n' "$t" >&2; exit 2 ;;
      esac
      key="${t%%=*}"
      version="${t#*=}"
      jq_args+=(--arg "k_$key" "$key" --arg "v_$key" "$version")
      jq_filter="$jq_filter | .tools[\$k_${key}] = \$v_${key}"
    done

    tmp="$(mktemp "$(dirname "$manifest")/.manifest.XXXXXX")"
    jq "${jq_args[@]}" "$jq_filter" "$manifest" >"$tmp"
    mv "$tmp" "$manifest"
    ;;
  *)
    printf 'error: unknown command: %s\n' "$cmd" >&2
    usage >&2
    exit 2
    ;;
esac
