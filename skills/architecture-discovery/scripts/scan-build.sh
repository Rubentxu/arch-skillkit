#!/usr/bin/env bash
# Build-system metadata scan (M2.3, pipeline Fase 3 of docs/07).
# Collects build metadata as raw evidence without running repository code:
# - Cargo.toml   → cargo metadata (resolves the graph; does not run build.rs)
# - package.json → raw copy (name/version/dependencies)
# - gradle/maven → detection only: their build scripts ARE repository code
#   and are never executed by default (docs/14)
#
# Usage: scan-build.sh [--repo <path>]
set -euo pipefail
SCRIPT_DIR="${BASH_SOURCE[0]%/*}"
[ "$SCRIPT_DIR" = "${BASH_SOURCE[0]}" ] && SCRIPT_DIR=.
# shellcheck source=lib/common.sh
. "$SCRIPT_DIR/lib/common.sh"

usage() {
  cat <<'EOF'
Usage: scan-build.sh [--repo <path>] [--run-id <id>]

Collects build-system metadata for the registered repository into
evidence/raw/build/. Opens and closes its own run manifest entry; the run
ends as partial when a detected build system's tool is unavailable.
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

if [ -n "$run_id_arg" ]; then
  # Orchestrated mode: the caller owns the run manifest lifecycle.
  run_id="$run_id_arg"
else
  run_id="$("$SCRIPT_DIR/run-manifest.sh" start --repo "$root")"
fi
commit="$(git -C "$root" rev-parse HEAD)"
evidence_dir="$workspace/evidence/raw/build"
mkdir -p "$evidence_dir"

# Each entry: {system, status: scanned|unavailable|detected, tool,
# tool_version, output?, note?}. Any unavailable system degrades the run.
entries=()
scan_status="success"
has_build_system=0

checksum_of() { sha256sum "$1" | cut -d' ' -f1; }

# --- Cargo ---------------------------------------------------------------
# cargo metadata writes Cargo.lock, which is a repository mutation (docs/14,
# UAT-001). Policy:
#   - Cargo.lock present  → --frozen: never writes, never touches the network;
#   - Cargo.lock missing  → resolve on a throwaway copy of the tree (minus
#     .git/target/node_modules) kept under the external workspace;
#   - drift/failure       → run degrades to partial.
run_cargo_metadata() { # $1: output json, $2: stderr log
  local out="$1" err="$2"
  if [ -f "$root/Cargo.lock" ]; then
    cargo metadata --format-version 1 --frozen >"$out" 2>"$err"
    return $?
  fi
  local snapshot="$evidence_dir/.cargo-snapshot"
  rm -rf "$snapshot"
  mkdir -p "$snapshot"
  (cd "$root" && tar --exclude=./.git --exclude=./target --exclude=./node_modules -cf - .) |
    (cd "$snapshot" && tar xf -)
  local rc=0
  (cd "$snapshot" && cargo metadata --format-version 1 >"$out" 2>"$err") || rc=$?
  rm -rf "$snapshot"
  return "$rc"
}

if [ -f "$root/Cargo.toml" ]; then
  has_build_system=1
  if command -v cargo >/dev/null 2>&1; then
    tool_version="$(cargo --version 2>/dev/null || printf 'unknown')"
    if run_cargo_metadata "$evidence_dir/cargo-metadata.json" "$evidence_dir/cargo.stderr.log"; then
      entries+=("$(jq -n --arg s scanned --arg t cargo --arg v "$tool_version" --arg o cargo-metadata.json \
        --arg c "$(checksum_of "$evidence_dir/cargo-metadata.json")" \
        '{system: "cargo", status: $s, tool: $t, tool_version: $v, output: $o, checksum: $c}')")
    else
      printf 'warning: cargo metadata failed; see %s\n' "$evidence_dir/cargo.stderr.log" >&2
      entries+=("$(jq -n --arg s failed --arg t cargo --arg v "$tool_version" \
        '{system: "cargo", status: $s, tool: $t, tool_version: $v, note: "cargo metadata failed"}')")
      scan_status="partial"
    fi
  else
    printf 'warning: cargo not available; skipping cargo metadata (install rust to scan Cargo projects fully)\n' >&2
    entries+=("$(jq -n --arg s unavailable --arg t cargo \
      '{system: "cargo", status: $s, tool: $t, tool_version: "absent", note: "cargo not on PATH"}')")
    scan_status="partial"
  fi
fi

# --- npm (package.json raw copy; dependency resolution is not run) --------
if [ -f "$root/package.json" ]; then
  has_build_system=1
  if jq -e . "$root/package.json" >/dev/null 2>&1; then
    cp "$root/package.json" "$evidence_dir/npm-package.json"
    entries+=("$(jq -n --arg s scanned --arg t npm --arg v "package.json" --arg o npm-package.json \
      --arg c "$(checksum_of "$evidence_dir/npm-package.json")" \
      '{system: "npm", status: $s, tool: $t, tool_version: $v, output: $o, checksum: $c, note: "raw manifest copy"}')")
  else
    printf 'warning: package.json is not valid JSON\n' >&2
    entries+=("$(jq -n --arg s failed --arg t npm \
      '{system: "npm", status: $s, tool: $t, note: "package.json is not valid JSON"}')")
    scan_status="partial"
  fi
fi

# --- Gradle / Maven: detection only, never executed ----------------------
if [ -f "$root/build.gradle.kts" ] || [ -f "$root/build.gradle" ]; then
  has_build_system=1
  entries+=("$(jq -n '{system: "gradle", status: "detected", tool: "gradle", tool_version: "not-run", note: "build scripts are repository code; dependency resolution is not run by default (docs/14)"}')")
fi
if [ -f "$root/pom.xml" ]; then
  has_build_system=1
  entries+=("$(jq -n '{system: "maven", status: "detected", tool: "maven", tool_version: "not-run", note: "build scripts are repository code; dependency resolution is not run by default (docs/14)"}')")
fi

if [ "$has_build_system" -eq 0 ]; then
  printf 'warning: no build systems detected in %s\n' "$root" >&2
fi

printf '%s' "${entries[@]:-}" | jq -s \
  --argjson sv 1 \
  --arg tool "build-metadata" \
  --arg commit "$commit" \
  --arg run_id "$run_id" \
  --arg recorded_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  '{
    schema_version: $sv,
    tool: $tool,
    tool_version: "mixed",
    commit: $commit,
    run_id: $run_id,
    recorded_at: $recorded_at,
    systems: .
  }' >"$evidence_dir/build.provenance.json"

record_args=(--scanner build-metadata)
if command -v cargo >/dev/null 2>&1; then
  record_args+=(--tool "cargo=$(cargo --version 2>/dev/null | head -n 1)")
fi
"$SCRIPT_DIR/run-manifest.sh" record "$run_id" "${record_args[@]}"

if [ -z "$run_id_arg" ]; then
  "$SCRIPT_DIR/run-manifest.sh" finish "$run_id" --status "$scan_status"
fi
printf 'scan-build: %s\nrun_id: %s\nevidence: %s\n' "$scan_status" "$run_id" "$evidence_dir"
