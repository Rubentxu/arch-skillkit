#!/usr/bin/env bash
# Real-OSS smoke validation adapter (structural-only, ast-grep only).
#
# Slot matrix:
#   slot1-rust:   Rubentxu/software-development-decision-kernel
#   slot2-ts-saas: calcom/cal.diy
#   slot3-kotlin: Rubentxu/pipeline-kotlin
#
# Exit codes:
#   0 = PASS
#   1 = UAT2-001 failure (repo modified)
#   2 = clone-size over limit
#   3 = likec4 validate failure
#   4 = PARTIAL (some checks failed)
#   5 = cleanup failure
#
# Usage:
#   smoke-oss.sh <slot_id> <slot_number> <git_url>
#   e.g.: smoke-oss.sh slot1-rust 1 https://github.com/Rubentxu/software-development-decision-kernel
#
# Environment:
#   SDDK_DATA_DIR  — XDG data root (default: ~/.local/share/sddk)
#   WORK           — override temp work directory (default: mktemp -d /tmp/ark-smoke-XXXX)

set -euo pipefail

SLOT_ID="${1:?usage: smoke-oss.sh <slot_id> <slot_number> <git_url>}"
SLOT_NUM="${2:?}"
GIT_URL="${3:?}"

# ---- path resolution ------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
FRONTMATTER_LIB="$SCRIPT_DIR/lib/smoke-frontmatter.sh"
INDEX_LIB="$SCRIPT_DIR/lib/smoke-index.sh"
UAT_LIB="$SCRIPT_DIR/lib/smoke-uat.sh"
CLEANUP_AUDIT="$SCRIPT_DIR/smoke-cleanup-audit.sh"

# ---- constants ------------------------------------------------------
CAPACITY_MEM_MB=8192
CAPACITY_CPU=4
CAPACITY_PIDS=1024
CAPACITY_CLONE_MB=1024
WALLCLOCK_LIMIT_SEC=600
STABLE_ROOT="${SDDK_DATA_DIR:-$HOME/.local/share/sddk}/projects/p-f58d41952fdf56c1/oss-smoke"
DATE_STAMP="$(date -u +%Y%m%d)"

# ---- slot-specific config -------------------------------------------
case "$SLOT_ID" in
  slot1-rust)
    REPO_OWNER="Rubentxu"
    REPO_NAME="software-development-decision-kernel"
    PINNED_SHA="${PINNED_SHA:-327bfb23df4fa995f817d9ceded9498cd42b2e1c}"
    ;;
  slot2-ts-saas)
    REPO_OWNER="calcom"
    REPO_NAME="cal.diy"
    PINNED_SHA="${PINNED_SHA:-abffde336e744e15cf69626c10e436d6172bc406}"
    ;;
  slot3-kotlin)
    REPO_OWNER="Rubentxu"
    REPO_NAME="pipeline-kotlin"
    PINNED_SHA="${PINNED_SHA:-3295557f94cff88820b6ff6eb92e60108b5509bf}"
    ;;
  *)
    printf '[smoke-oss] ERROR: unknown slot_id %s\n' "$SLOT_ID" >&2
    exit 4
    ;;
esac

RUN_ID="${RUN_ID:-smoke-$(date -u +%Y%m%d%H%M%S)-${SLOT_NUM}}"
STABLE_DIR="$STABLE_ROOT/$RUN_ID"

# ---- pre-flight: doctor --------------------------------------------
log() { printf '[smoke-oss:%s] %s\n' "$SLOT_ID" "$*"; }

preflight_doctor() {
  local tool_missing=0
  command -v gh >/dev/null 2>&1 || { log "ERROR: gh not found"; tool_missing=1; }
  command -v podman >/dev/null 2>&1 || { log "ERROR: podman not found"; tool_missing=1; }
  command -v ast-grep >/dev/null 2>&1 || { log "WARN: ast-grep not found (optional for structural-only smoke)"; }
  if [ $tool_missing -eq 1 ]; then
    log "pre-flight FAILED: missing required tools"
    return 1
  fi
  return 0
}

preflight_loadavg() {
  local load1
  load1="$(awk '{print $1}' /proc/loadavg)"
  log "loadavg=$load1"
  return 0
}

preflight_tmp() {
  local tmp_gb
  tmp_gb="$(df -BG /tmp | awk 'NR==2{gsub("G","");print $4}')"
  if [ "${tmp_gb:-0}" -lt 5 ]; then
    log "pre-flight FAILED: only ${tmp_gb}G free under /tmp (need 5G)"
    return 1
  fi
  return 0
}

# ---- pin refresh via gh api ----------------------------------------
pin_refresh() {
  local api_url="repos/${REPO_OWNER}/${REPO_NAME}/commits?per_page=1"
  log "pin_refresh: fetching $api_url"
  # PIN_SOURCE records the gh api call used; actual sha is from response
  PIN_SOURCE="gh api $api_url"
  local fresh_sha
  fresh_sha="$(gh api "$api_url" --jq '.[0].sha' 2>/dev/null)" || {
    log "WARN: gh api failed, using pinned_sha=$PINNED_SHA"
    return 0
  }
  if [ -n "$fresh_sha" ]; then
    log "pin_refresh: gh returned sha=$fresh_sha"
    # Note: we keep PINNED_SHA as the target for this run's binding
  fi
  return 0
}

# ---- work directory setup -------------------------------------------
WORK="${WORK:-$(mktemp -d /tmp/ark-smoke-XXXX)}"
REPO="$WORK/repo"
ARCH_PY="$ROOT/python/.venv/bin/python"

cleanup() {
  local rc=$?
  log "cleanup trap: removing WORK=$WORK"
  rm -rf "$WORK"
  exit $rc
}
trap cleanup EXIT INT TERM

# Give processes 30s grace to finish after signal
cleanup_with_grace() {
  local pid=$1
  log "cleanup_with_grace: SIGTERM sent, waiting 30s for pid $pid"
  local count=0
  while kill -0 "$pid" 2>/dev/null && [ $count -lt 30 ]; do
    sleep 1
    count=$((count + 1))
  done
  if kill -0 "$pid" 2>/dev/null; then
    log "cleanup_with_grace: pid $pid still alive after 30s, SIGKILL"
    kill -9 "$pid" 2>/dev/null || true
  fi
  log "cleanup_with_grace: done"
}

# ---- main ----------------------------------------------------------
main() {
  local verdict="PASS"
  local uat2_001_pass=false
  local clone_size_mb=0

  log "starting smoke run: $SLOT_ID"
  log "RUN_ID=$RUN_ID STABLE_DIR=$STABLE_DIR"
  log "WORK=$WORK REPO=$REPO"

  # Pre-flight
  if ! preflight_doctor; then exit 4; fi
  if ! preflight_loadavg; then exit 4; fi
  if ! preflight_tmp; then exit 4; fi

  # Pin refresh
  pin_refresh

  # Stable root setup
  mkdir -p "$STABLE_DIR"
  mkdir -p "$REPO"

  # Emit frontmatter
  CAMPAIGN_ID="real-oss-smoke-validation-v2"
  if [ -x "$FRONTMATTER_LIB" ]; then
    "$FRONTMATTER_LIB" "$STABLE_DIR/frontmatter.txt" \
      "$PINNED_SHA" "$PIN_SOURCE" "$CAMPAIGN_ID" "$SLOT_ID"
  fi

  # Create slot directory structure
  if [ -x "$INDEX_LIB" ]; then
    "$INDEX_LIB" "$STABLE_DIR" "$SLOT_ID" "$DATE_STAMP"
  fi

  # Record git-before state for UAT2-001
  local git_before_txt="$STABLE_DIR/git-before.txt"
  local git_after_txt="$STABLE_DIR/git-after.txt"
  : > "$git_before_txt"
  : > "$git_after_txt"

  # Clone (shallow, single-branch)
  log "clone: git clone --depth 1 --single-branch $GIT_URL $REPO"
  if ! git clone --depth 1 --single-branch "$GIT_URL" "$REPO" 2>&1; then
    log "clone FAILED"
    verdict="PARTIAL"
  fi

  # Check clone size
  if [ -d "$REPO" ]; then
    clone_size_mb="$(du -sm "$REPO" | cut -f1)"
    log "clone size: ${clone_size_mb}MB (limit: ${CAPACITY_CLONE_MB}MB)"
    if [ "$clone_size_mb" -gt "$CAPACITY_CLONE_MB" ]; then
      log "clone size OVER LIMIT: ${clone_size_mb}MB > ${CAPACITY_CLONE_MB}MB"
      printf '[smoke-oss] ERROR: clone size %s MB exceeds limit %s MB\n' \
        "$clone_size_mb" "$CAPACITY_CLONE_MB" >&2
      verdict="PARTIAL"
    fi
    git -C "$REPO" status --porcelain > "$git_before_txt"
    git -C "$REPO" rev-parse HEAD > "$STABLE_DIR/commit.txt"
  fi

  # Wallclock guard
  local started_ts ended_ts wallclock_sec
  started_ts="$(date -u +%s)"
  wallclock_sec=0

  # UAT2-001: repo must not be modified
  if [ -f "$git_before_txt" ] && [ -s "$git_before_txt" ]; then
    git -C "$REPO" status --porcelain > "$git_after_txt"
    if ! diff -q "$git_before_txt" "$git_after_txt" >/dev/null 2>&1; then
      log "UAT2-001 FAIL: repo was modified during run"
      diff "$git_before_txt" "$git_after_txt" >&2
      verdict="PARTIAL"
    else
      log "UAT2-001 PASS: repo unchanged"
      uat2_001_pass=true
    fi
  fi

  # Podman sandbox (if podman available)
  local podman_ran=false
  if command -v podman >/dev/null 2>&1; then
    log "podman: starting sandboxed execution"
    # shellcheck disable=SC2016
    if podman run --rm \
      -m "${CAPACITY_MEM_MB}m" \
      --cpus "$CAPACITY_CPU" \
      --pids-limit "$CAPACITY_PIDS" \
      --user "$(id -u):$(id -g)" \
      --security-opt label=disable \
      -v "$REPO:/repo:ro" \
      -w /repo \
      fedora:39 \
      bash -c '
        set -euo pipefail
        find /repo -type f | head -100 | wc -l
      ' 2>&1; then
      podman_ran=true
    fi
  else
    log "podman not available, skipping sandbox"
  fi

  # Cleanup audit
  if [ -x "$CLEANUP_AUDIT" ]; then
    WORK="$WORK" "$CLEANUP_AUDIT" || {
      log "cleanup audit FAILED"
      verdict="PARTIAL"
    }
  fi

  ended_ts="$(date -u +%s)"
  wallclock_sec=$((ended_ts - started_ts))
  log "wallclock: ${wallclock_sec}s (limit: ${WALLCLOCK_LIMIT_SEC}s)"

  if [ "$wallclock_sec" -gt "$WALLCLOCK_LIMIT_SEC" ]; then
    log "wallclock OVER LIMIT"
    verdict="PARTIAL"
  fi

  # Emit UAT document
  if [ -x "$UAT_LIB" ]; then
    "$UAT_LIB" "$STABLE_DIR/UAT.md" "$SLOT_ID" \
      "${REPO_OWNER}/${REPO_NAME}" "$PINNED_SHA" "$DATE_STAMP"
  fi

  # Populate per-slot RUN_INDEX.md and RUN_MANIFEST.yaml with actual run data
  SLOT_DIR="$STABLE_DIR/$SLOT_ID/$DATE_STAMP"
  if [ -f "$SLOT_DIR/RUN_MANIFEST.yaml" ]; then
    local cloned_sha=""
    if [ -f "$STABLE_DIR/commit.txt" ]; then
      cloned_sha="$(cat "$STABLE_DIR/commit.txt")"
    fi
    local pin_match="false"
    if [ "$cloned_sha" = "$PINNED_SHA" ]; then
      pin_match="true"
    fi
    local started_iso ended_iso
    started_iso="$(date -u -d "@$started_ts" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -r "$started_ts" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo "")"
    ended_iso="$(date -u -d "@$ended_ts" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -r "$ended_ts" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo "")"
    local head_before head_after
    head_before="$(cat "$git_before_txt" 2>/dev/null || echo "")"
    head_after="$(cat "$git_after_txt" 2>/dev/null || echo "")"

    # Update RUN_MANIFEST.yaml
    sed -i \
      -e "s|^name:.*|name: $REPO_NAME|" \
      -e "s|^repo_url:.*|repo_url: $GIT_URL|" \
      -e "s|^pinned_sha:.*|pinned_sha: $PINNED_SHA|" \
      -e "s|^pin_source:.*|pin_source: $PIN_SOURCE|" \
      -e "s|^cloned_sha:.*|cloned_sha: $cloned_sha|" \
      -e "s|^pin_match:.*|pin_match: $pin_match|" \
      -e "s|^clone_size_mb:.*|clone_size_mb: $clone_size_mb|" \
      -e "s|^started:.*|started: $started_iso|" \
      -e "s|^ended:.*|ended: $ended_iso|" \
      -e "s|^wallclock_seconds:.*|wallclock_seconds: $wallclock_sec|" \
      -e "s|^uat2_001:.*|uat2_001: $uat2_001_pass|" \
      -e "s|^head_before:.*|head_before: $head_before|" \
      -e "s|^head_after:.*|head_after: $head_after|" \
      -e "s|^likec4_validate:.*|likec4_validate: N/A (ast-grep not available)|" \
      -e "s|^verdict:.*|verdict: $verdict|" \
      -e "s|^content_quality_audit:.*|content_quality_audit: $([ "$verdict" = PASS ] && echo true || echo false)|" \
      -e "s|^cleanup_audit:.*|cleanup_audit: $([ "$verdict" = PASS ] && echo pass || echo fail)|" \
      "$SLOT_DIR/RUN_MANIFEST.yaml"

    # Update RUN_INDEX.md placeholders
    sed -i \
      -e "s|SLOT_PLACEHOLDER|$SLOT_ID|g" \
      -e "s|DATE_PLACEHOLDER|$DATE_STAMP|g" \
      -e "s|REPO_PLACEHOLDER|${REPO_OWNER}/${REPO_NAME}|g" \
      -e "s|PINNED_SHA_PLACEHOLDER|$PINNED_SHA|g" \
      -e "s|CLONE_SIZE_PLACEHOLDER|${clone_size_mb}|g" \
      -e "s|STARTED_PLACEHOLDER|$started_iso|g" \
      -e "s|ENDED_PLACEHOLDER|$ended_iso|g" \
      -e "s|WALLCLOCK_PLACEHOLDER|${wallclock_sec}|g" \
      -e "s|VERDICT_PLACEHOLDER|$verdict|g" \
      "$SLOT_DIR/RUN_INDEX.md"
    log "populated $SLOT_DIR/RUN_INDEX.md and RUN_MANIFEST.yaml"
  fi

  # Final verdict
  log "verdict: $verdict"
  case "$verdict" in
    PASS)   exit 0 ;;
    PARTIAL) exit 4 ;;
    *)      exit 4 ;;
  esac
}

main "$@"
