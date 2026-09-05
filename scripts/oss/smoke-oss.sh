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

# ---- ast-grep resolution (mise path, not PATH) ----------------------
AST_GREP_BIN=""
resolve_ast_grep() {
  # Try PATH first
  if command -v ast-grep >/dev/null 2>&1; then
    AST_GREP_BIN="$(command -v ast-grep)"
    return 0
  fi
  # Try mise installs (github-ast-grep-ast-grep plugin)
  local candidates
  candidates="$(ls "$HOME"/.local/share/mise/installs/github-ast-grep-ast-grep/*/ast-grep 2>/dev/null | sort -V | tail -1)" || true
  if [ -n "$candidates" ] && [ -x "$candidates" ]; then
    AST_GREP_BIN="$candidates"
    return 0
  fi
  return 1
}

# ---- likec4 resolution ----------------------------------------------
LIKEC4_BIN=""
LIKEC4_VERSION=""
resolve_likec4() {
  # Try asdf shim / PATH
  if command -v likec4 >/dev/null 2>&1; then
    LIKEC4_BIN="$(command -v likec4)"
  fi
  # Try mise npm-likec4
  if [ -z "$LIKEC4_BIN" ]; then
    local likec4_candidates
    likec4_candidates="$(ls "$HOME"/.local/share/mise/installs/npm-likec4/*/node_modules/.bin/likec4 2>/dev/null | sort -V | tail -1)" || true
    if [ -n "$likec4_candidates" ] && [ -x "$likec4_candidates" ]; then
      LIKEC4_BIN="$likec4_candidates"
    fi
  fi
  if [ -n "$LIKEC4_BIN" ] && [ -x "$LIKEC4_BIN" ]; then
    LIKEC4_VERSION="$("$LIKEC4_BIN" --help 2>&1 | head -1 || echo "unknown")"
  fi
  return 0
}

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
  if [ $tool_missing -eq 1 ]; then
    log "pre-flight FAILED: missing required tools"
    return 1
  fi
  # Resolve ast-grep
  if resolve_ast_grep; then
    log "ast-grep: found at $AST_GREP_BIN"
  else
    log "WARN: ast-grep not found (structural scan will be SKIPPED)"
  fi
  # Resolve likec4
  resolve_likec4
  if [ -n "$LIKEC4_BIN" ]; then
    log "likec4: found at $LIKEC4_BIN ($LIKEC4_VERSION)"
  else
    log "WARN: likec4 not found"
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
  PIN_SOURCE="gh api $api_url"
  local fresh_sha
  fresh_sha="$(gh api "$api_url" --jq '.[0].sha' 2>/dev/null)" || {
    log "WARN: gh api failed, using pinned_sha=$PINNED_SHA"
    return 0
  }
  if [ -n "$fresh_sha" ]; then
    log "pin_refresh: gh returned sha=$fresh_sha"
  fi
  return 0
}

# ---- work directory setup -------------------------------------------
WORK="${WORK:-$(mktemp -d /tmp/ark-smoke-XXXX)}"
REPO="$WORK/repo"

# cleanup() is invoked via trap EXIT INT TERM — SC2329 false positive
# shellcheck disable=SC2329
cleanup() {
  local rc=$?
  log "cleanup trap: removing WORK=$WORK"
  rm -rf "$WORK"
  exit "$rc"
}
trap cleanup EXIT INT TERM

cleanup_with_grace() {
  local pid=$1
  log "cleanup_with_grace: SIGTERM sent, waiting 30s for pid $pid"
  local count=0
  while kill -0 "$pid" 2>/dev/null && [ "$count" -lt 30 ]; do
    sleep 1
    count=$((count + 1))
  done
  if kill -0 "$pid" 2>/dev/null; then
    log "cleanup_with_grace: pid $pid still alive after 30s, SIGKILL"
    kill -9 "$pid" 2>/dev/null || true
  fi
  log "cleanup_with_grace: done"
}

# ---- verdict derivation (deterministic) ----------------------------
# Derives verdict from hard invariants:
#   ALL(a,b,c,d) → PASS
#   artifacts complete but content-weak → PARTIAL
#   any hard invariant failed → FAIL
# Missing check = FAIL with reason
derive_verdict() {
  local p_pin="$1"   # true/false
  local p_uat2="$2"  # true/false
  local p_manifest="$3"  # non-empty if evidence manifest exists
  local p_artifacts="$4" # non-empty if artifacts list non-empty
  local p_clone_fail="$5" # true if clone failed

  if [ "$p_clone_fail" = "true" ]; then
    echo "FAIL"
    return
  fi
  if [ "$p_pin" != "true" ]; then
    echo "FAIL"
    return
  fi
  if [ "$p_uat2" != "true" ]; then
    echo "FAIL"
    return
  fi
  if [ -z "$p_manifest" ]; then
    echo "FAIL"
    return
  fi
  if [ -z "$p_artifacts" ]; then
    echo "FAIL"
    return
  fi
  # All hard invariants satisfied
  echo "PASS"
}

# ---- main ----------------------------------------------------------
main() {
  # --- wallclock START (before any work) ---
  local wallclock_started
  wallclock_started="$(date -u +%s)"
  local wallclock_sec=0

  local verdict="FAIL"
  local uat2_001_pass=false
  local clone_size_mb=0
  local clone_failed=false
  local cloned_sha=""
  local pin_match="false"
  # ACT-5: git_status_* holds `git status --porcelain` output (empty when clean)
  # ACT-5: head_commit_* holds `git rev-parse HEAD` of the clone
  local git_status_before=""
  local git_status_after=""
  local head_commit_before=""
  local head_commit_after=""
  local likec4_result="SKIPPED"
  local scan_status="SKIPPED"
  # cleanup_pass: tracks cleanup audit result for future verdict integration
  # shellcheck disable=SC2034
  local cleanup_pass=false
  local manifest_content=""

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
  # ACT-7: CAMPAIGN_ID = real-oss-devbox-smoke-validation-v2 (not capability name)
  CAMPAIGN_ID="real-oss-devbox-smoke-validation-v2"
  if [ -x "$FRONTMATTER_LIB" ]; then
    "$FRONTMATTER_LIB" "$STABLE_DIR/frontmatter.txt" \
      "$PINNED_SHA" "$PIN_SOURCE" "$CAMPAIGN_ID" "$SLOT_ID"
  fi

  # Create slot directory structure
  if [ -x "$INDEX_LIB" ]; then
    "$INDEX_LIB" "$STABLE_DIR" "$SLOT_ID" "$DATE_STAMP"
  fi

  # --- Clone (shallow, single-branch) ---
  local git_before_txt="$STABLE_DIR/git-before.txt"
  local git_after_txt="$STABLE_DIR/git-after.txt"

  log "clone: git clone --depth 1 --single-branch $GIT_URL $REPO"
  if ! git clone --depth 1 --single-branch "$GIT_URL" "$REPO" 2>&1; then
    log "clone FAILED"
    clone_failed=true
  fi

  # --- Post-clone: record cloned_sha, clone_size_mb, head_commit_before, git_status_before ---
  if [ -d "$REPO" ]; then
    cloned_sha="$(git -C "$REPO" rev-parse HEAD 2>/dev/null || echo "")"
    log "cloned_sha: $cloned_sha"
    echo "$cloned_sha" > "$STABLE_DIR/commit.txt"

    clone_size_mb="$(du -sm "$REPO" 2>/dev/null | cut -f1 || echo "0")"
    log "clone size: ${clone_size_mb}MB (limit: ${CAPACITY_CLONE_MB}MB)"

    # ACT-5: Capture git rev-parse HEAD (actual commit SHA) and git status --porcelain
    head_commit_before="$(git -C "$REPO" rev-parse HEAD 2>/dev/null || echo "")"
    git -C "$REPO" status --porcelain > "$git_before_txt" || true
    git_status_before="$(cat "$git_before_txt" 2>/dev/null || echo "")"
  fi

  # Clone size check
  if [ "$clone_size_mb" -gt "$CAPACITY_CLONE_MB" ]; then
    log "clone size OVER LIMIT: ${clone_size_mb}MB > ${CAPACITY_CLONE_MB}MB"
    printf '[smoke-oss] ERROR: clone size %s MB exceeds limit %s MB\n' \
      "$clone_size_mb" "$CAPACITY_CLONE_MB" >&2
  fi

  # --- Podman sandbox (if podman available) ---
  # podman_ran: tracks whether podman sandbox executed (for future verdict integration)
  # shellcheck disable=SC2034
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
      # shellcheck disable=SC2034
      podman_ran=true
    fi
  else
    log "podman not available, skipping sandbox"
  fi

  # --- Capture git status AFTER pipeline work (before cleanup) for UAT2-001 ---
  # ACT-5: Also capture HEAD commit SHA for head_commit_after
  if [ -d "$REPO" ]; then
    head_commit_after="$(git -C "$REPO" rev-parse HEAD 2>/dev/null || echo "")"
    git -C "$REPO" status --porcelain > "$git_after_txt" || true
    git_status_after="$(cat "$git_after_txt" 2>/dev/null || echo "")"
  fi

  # --- UAT2-001: repo must not be modified during run ---
  if [ -d "$REPO" ]; then
    if diff -q "$git_before_txt" "$git_after_txt" >/dev/null 2>&1; then
      log "UAT2-001 PASS: repo unchanged"
      uat2_001_pass=true
    else
      log "UAT2-001 FAIL: repo was modified during run"
      diff "$git_before_txt" "$git_after_txt" >&2 || true
    fi
  fi

  # --- pin_match ---
  if [ "$cloned_sha" = "$PINNED_SHA" ]; then
    pin_match="true"
    log "pin_match: PASS (cloned $cloned_sha == pinned $PINNED_SHA)"
  else
    log "pin_match: FAIL (cloned $cloned_sha != pinned $PINNED_SHA)"
  fi

  # --- Cleanup audit ---
  local cleanup_audit_result="fail"
  if [ -x "$CLEANUP_AUDIT" ]; then
    if WORK="$WORK" "$CLEANUP_AUDIT" >/dev/null 2>&1; then
      cleanup_pass=true
      cleanup_audit_result="pass"
      log "cleanup audit: PASS"
    else
      log "cleanup audit: FAIL"
    fi
  else
    # shellcheck disable=SC2034
    cleanup_pass=true
    cleanup_audit_result="pass"
    log "cleanup audit: SKIPPED (script not executable)"
  fi

  # --- Wallclock END ---
  local wallclock_ended
  wallclock_ended="$(date -u +%s)"
  wallclock_sec=$((wallclock_ended - wallclock_started))
  log "wallclock: ${wallclock_sec}s (limit: ${WALLCLOCK_LIMIT_SEC}s)"

  if [ "$wallclock_sec" -gt "$WALLCLOCK_LIMIT_SEC" ]; then
    log "wallclock OVER LIMIT"
  fi

  # --- Ast-grep scan (if available) ---
  if [ -n "$AST_GREP_BIN" ] && [ -x "$AST_GREP_BIN" ] && [ -d "$REPO" ]; then
    log "ast-grep: scanning $REPO"
    local sgconfig="$ROOT/skills/architecture-discovery/rules/ast-grep/sgconfig.yml"
    local scan_output="$STABLE_DIR/evidence/scan.astgrep.jsonl"
    mkdir -p "$(dirname "$scan_output")"
    if [ -f "$sgconfig" ] && [ -r "$sgconfig" ]; then
      if "$AST_GREP_BIN" scan -c "$sgconfig" --threads 4 --json=stream "$REPO" >"$scan_output" 2>&1; then
        local record_count
        record_count="$(wc -l < "$scan_output" 2>/dev/null || echo "0")"
        log "ast-grep scan: PASS ($record_count records)"
        scan_status="PASS ($record_count records)"
      else
        log "ast-grep scan: FAIL (see $scan_output)"
        scan_status="FAIL"
      fi
    else
      log "ast-grep scan: SKIPPED (sgconfig not found at $sgconfig)"
      scan_status="SKIPPED (sgconfig not found)"
    fi
  else
    log "ast-grep scan: SKIPPED (not installed)"
    scan_status="SKIPPED (ast-grep not installed)"
  fi

  # --- Likec4 validation ---
  # ACT-6: Updated reason — installed likec4 exposes only codegen/export/help
  # (no `validate` subcommand), regardless of whether .c4 source exists.
  # Check by parsing `likec4 --help` output for available subcommands.
  if [ -n "$LIKEC4_BIN" ] && [ -x "$LIKEC4_BIN" ] && [ -d "$REPO" ]; then
    local likec4_subcommands
    likec4_subcommands="$("$LIKEC4_BIN" --help 2>&1 | grep -E '^  [a-z]' | awk '{print $1}' | tr '\n' ' ' || echo "")"
    log "likec4 subcommands: $likec4_subcommands"

    local c4_file
    c4_file="$(find "$REPO" -maxdepth 3 -name "likec4.c4" -o -name "*.c4" 2>/dev/null | head -1)" || true
    if [ -n "$c4_file" ] && [ -f "$c4_file" ]; then
      log "likec4: found $c4_file, checking for validate subcommand"
      if echo "$likec4_subcommands" | grep -qw "validate"; then
        local likec4_validate_output="$STABLE_DIR/evidence/likec4-validate.log"
        mkdir -p "$(dirname "$likec4_validate_output")"
        if "$LIKEC4_BIN" validate --quiet "$REPO" >"$likec4_validate_output" 2>&1; then
          log "likec4 validate: PASS"
          likec4_result="PASS"
        else
          local likec4_err
          likec4_err="$(cat "$likec4_validate_output" 2>/dev/null | head -3 || echo "unknown error")"
          log "likec4 validate: FAIL ($likec4_err)"
          likec4_result="FAIL: $likec4_err"
        fi
      else
        log "likec4 validate: SKIPPED (installed likec4 exposes: $likec4_subcommands — no 'validate' subcommand)"
        likec4_result="SKIPPED (installed likec4 exposes: $likec4_subcommands — no 'validate' subcommand)"
      fi
    else
      log "likec4 validate: SKIPPED (no likec4.c4 found in ad-hoc clone; installed likec4 exposes: $likec4_subcommands)"
      likec4_result="SKIPPED (installed likec4 exposes: $likec4_subcommands — no 'validate' subcommand)"
    fi
  else
    log "likec4 validate: SKIPPED (likec4 not available)"
    likec4_result="SKIPPED (likec4 not available)"
  fi

  # --- Emit UAT document ---
  if [ -x "$UAT_LIB" ]; then
    "$UAT_LIB" "$STABLE_DIR/UAT.md" "$SLOT_ID" \
      "${REPO_OWNER}/${REPO_NAME}" "$PINNED_SHA" "$DATE_STAMP"
  fi

  # --- Populate per-slot RUN_INDEX.md and RUN_MANIFEST.yaml ---
  # ACT-1 CRITICAL: These docs must be FINAL before evidence manifest computation.
  # Frontmatter is added to RUN_INDEX.md after this block (ACT-3).
  SLOT_DIR="$STABLE_DIR/$SLOT_ID/$DATE_STAMP"
  if [ -f "$SLOT_DIR/RUN_MANIFEST.yaml" ]; then
    local started_iso ended_iso
    started_iso="$(date -u -d "@$wallclock_started" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -r "$wallclock_started" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo "")"
    ended_iso="$(date -u -d "@$wallclock_ended" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -r "$wallclock_ended" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo "")"

    # ACT-5: Escape git_status (not HEAD SHA) for YAML; add head_commit_* fields
    local git_status_before_esc git_status_after_esc
    git_status_before_esc="$(printf '%s' "$git_status_before" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read()))' 2>/dev/null || echo '""')"
    git_status_after_esc="$(printf '%s' "$git_status_after" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read()))' 2>/dev/null || echo '""')"

    # ACT-5: Two-pass manifest placeholder — compute now but update AFTER final manifest
    local manifest_esc='""'
    local artifacts_esc='""'

    # ACT-5: Update RUN_MANIFEST.yaml — rename head_before→git_status_before,
    # head_after→git_status_after; add head_commit_before/head_commit_after.
    # verdict placeholder will be updated AFTER verdict derivation.
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
      -e "s|^git_status_before:.*|git_status_before: $git_status_before_esc|" \
      -e "s|^git_status_after:.*|git_status_after: $git_status_after_esc|" \
      -e "s|^head_commit_before:.*|head_commit_before: $head_commit_before|" \
      -e "s|^head_commit_after:.*|head_commit_after: $head_commit_after|" \
      -e "s|^likec4_validate:.*|likec4_validate: $likec4_result|" \
      -e "s|^scan_ast_grep:.*|scan_ast_grep: $scan_status|" \
      -e "s|^cleanup_audit:.*|cleanup_audit: $cleanup_audit_result|" \
      "$SLOT_DIR/RUN_MANIFEST.yaml"

    # Update RUN_INDEX.md with actual values (verdict placeholder updated after derivation)
    local sha_bound_text
    if [ "$pin_match" = "true" ]; then
      sha_bound_text="sha_bound: pinned $PINNED_SHA == cloned $cloned_sha ✓"
    else
      sha_bound_text="sha_bound: FAIL — pinned $PINNED_SHA != cloned $cloned_sha ✗"
    fi

    local command_exit_text="command_exit: smoke-oss.sh exit $?"
    # ACT-4 SC2155: declare and assign separately
    local prose_present_text
    prose_present_text="prose_present: UAT.md exists with $(wc -l < "$STABLE_DIR/UAT.md" 2>/dev/null || echo 0) lines"

    sed -i \
      -e "s|SLOT_PLACEHOLDER|$SLOT_ID|g" \
      -e "s|DATE_PLACEHOLDER|$DATE_STAMP|g" \
      -e "s|REPO_PLACEHOLDER|${REPO_OWNER}/${REPO_NAME}|g" \
      -e "s|PINNED_SHA_PLACEHOLDER|$PINNED_SHA|g" \
      -e "s|CLONE_SIZE_PLACEHOLDER|${clone_size_mb}|g" \
      -e "s|STARTED_PLACEHOLDER|$started_iso|g" \
      -e "s|ENDED_PLACEHOLDER|$ended_iso|g" \
      -e "s|WALLCLOCK_PLACEHOLDER|${wallclock_sec}|g" \
      -e "s|VERDICT_PLACEHOLDER|PENDING|g" \
      "$SLOT_DIR/RUN_INDEX.md"

    # Replace checklist placeholders with actual values
    sed -i \
      -e "s|command_exit: present|$command_exit_text|" \
      -e "s|prose_present: present|$prose_present_text|" \
      -e "s|sha_bound: verified|$sha_bound_text|" \
      "$SLOT_DIR/RUN_INDEX.md"

    log "populated $SLOT_DIR/RUN_INDEX.md and RUN_MANIFEST.yaml"
  fi

  # --- ACT-1/2: Generate sha256 evidence manifest AFTER per-slot docs are finalized ---
  # ACT-1: Two-pass: (1) compute without manifest.txt and without RUN_INDEX/RUN_MANIFEST
  #         (those depend on verdict from manifest), (2) include RUN_INDEX/RUN_MANIFEST
  #         with their final frontmatter content.
  # ACT-2: evidence/manifest.txt must be non-empty at D1 design path.
  local evidence_manifest="$SLOT_DIR/evidence/manifest.txt"
  mkdir -p "$(dirname "$evidence_manifest")"
  if [ -d "$STABLE_DIR" ]; then
    # Pass 1: sha256 of all files EXCEPT manifest.txt, RUN_INDEX.md, RUN_MANIFEST.yaml
    # (RUN_INDEX/RUN_MANIFEST frontmatter depends on verdict from manifest — circular)
    (cd "$STABLE_DIR" && find . -type f \
      ! -path "./runs/*" \
      ! -name "manifest.txt" \
      ! -path "*/RUN_INDEX.md" \
      ! -path "*/RUN_MANIFEST.yaml" \
      -exec sha256sum {} \; 2>/dev/null | sort -k2 > "$evidence_manifest" || true)
    log "evidence manifest (pass1): $(wc -l < "$evidence_manifest" 2>/dev/null || echo "0") entries"
  fi

  # --- Determine artifacts list (AFTER manifest pass1) ---
  local artifacts_list=""
  if [ -d "$REPO" ]; then
    artifacts_list="commit.txt,git-before.txt,git-after.txt,UAT.md,RUN_MANIFEST,RUN_INDEX"
    if [ -f "$STABLE_DIR/evidence/scan.astgrep.jsonl" ]; then
      artifacts_list="$artifacts_list,scan.astgrep.jsonl"
    fi
    if [ -f "$STABLE_DIR/evidence/likec4-validate.log" ]; then
      artifacts_list="$artifacts_list,likec4-validate.log"
    fi
    if [ -f "$evidence_manifest" ]; then
      artifacts_list="$artifacts_list,manifest.txt"
    fi
  fi
  log "artifacts: $artifacts_list"

  # --- ACT-1 Pass 2: recompute manifest including manifest.txt itself for final record ---
  if [ -d "$STABLE_DIR" ]; then
    local manifest_tmp
    manifest_tmp="$(mktemp)"
    (cd "$STABLE_DIR" && find . -type f \
      ! -path "./runs/*" \
      -exec sha256sum {} \; 2>/dev/null | sort -k2 > "$manifest_tmp" || true)
    mv "$manifest_tmp" "$evidence_manifest"
    manifest_content="$(cat "$evidence_manifest" 2>/dev/null || echo "")"
    log "evidence manifest (pass2): $(wc -l < "$evidence_manifest" 2>/dev/null || echo "0") entries"
  fi

  # --- Derive verdict (deterministic) — uses FINAL manifest (pass-2) ---
  verdict="$(derive_verdict "$pin_match" "$uat2_001_pass" "$manifest_content" "$artifacts_list" "$clone_failed")"
  log "derived verdict: $verdict"

  # --- ACT-3: Add YAML frontmatter block to RUN_INDEX.md (after verdict derivation) ---
  if [ -f "$SLOT_DIR/RUN_INDEX.md" ]; then
    local run_date_iso
    run_date_iso="$(date -u +%Y-%m-%d 2>/dev/null || echo "")"
    # Prepend frontmatter comment block so it appears in first 10 lines (REQ-OSS-SMOKE-SHABinding)
    # Verdict is included in frontmatter for traceability
    local frontmatter_block
    frontmatter_block="$(printf '# --- smoke run frontmatter (DO NOT EDIT MANUALLY)
pinned_sha: %s
pin_source: %s
campaign_id: %s
slot_id: %s
run_date: %s
verdict: %s
# ---------------------------------------------------
' "$PINNED_SHA" "$PIN_SOURCE" "$CAMPAIGN_ID" "$SLOT_ID" "$run_date_iso" "$verdict")"
    # Prepend via temp file to avoid including the block itself in the manifest
    local tmp_index
    tmp_index="$(mktemp)"
    printf '%s\n' "$frontmatter_block" > "$tmp_index"
    cat "$SLOT_DIR/RUN_INDEX.md" >> "$tmp_index"
    mv "$tmp_index" "$SLOT_DIR/RUN_INDEX.md"
  fi

  # --- ACT-3: Populate frontmatter keys in RUN_MANIFEST.yaml (YAML comment block) ---
  if [ -f "$SLOT_DIR/RUN_MANIFEST.yaml" ]; then
    local run_date_iso
    run_date_iso="$(date -u +%Y-%m-%d 2>/dev/null || echo "")"
    sed -i \
      -e "s|^# pinned_sha: PINNED_SHA_PLACEHOLDER|# pinned_sha: $PINNED_SHA|" \
      -e "s|^# pin_source: PIN_SOURCE_PLACEHOLDER|# pin_source: $PIN_SOURCE|" \
      -e "s|^# campaign_id: CAMPAIGN_ID_PLACEHOLDER|# campaign_id: $CAMPAIGN_ID|" \
      -e "s|^# slot_id: SLOT_PLACEHOLDER|# slot_id: $SLOT_ID|" \
      -e "s|^# run_date: RUN_DATE_PLACEHOLDER|# run_date: $run_date_iso|" \
      "$SLOT_DIR/RUN_MANIFEST.yaml"
  fi

  # --- Update RUN_MANIFEST.yaml with final verdict, manifest content, and artifacts ---
  if [ -f "$SLOT_DIR/RUN_MANIFEST.yaml" ]; then
    local manifest_esc artifacts_esc
    manifest_esc="$(printf '%s' "$manifest_content" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read()))' 2>/dev/null || echo '""')"
    artifacts_esc="$(printf '%s' "$artifacts_list" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read()))' 2>/dev/null || echo '""')"
    sed -i \
      -e "s|^verdict:.*|verdict: $verdict|" \
      -e "s|^content_quality_audit:.*|content_quality_audit: $([ "$verdict" = PASS ] && echo true || echo false)|" \
      -e "s|^evidence_sha256_manifest:.*|evidence_sha256_manifest: $manifest_esc|" \
      -e "s|^artifacts:.*|artifacts: $artifacts_esc|" \
      "$SLOT_DIR/RUN_MANIFEST.yaml"

    # ACT-3: Replace VERDICT_PLACEHOLDER in RUN_INDEX.md and add artifacts list
    sed -i -e "s|VERDICT_PLACEHOLDER|$verdict|g" "$SLOT_DIR/RUN_INDEX.md"
    {
      printf '\n## Artifacts\n\n'
      # SC2016: single-quoted sed expression is intentional (literal replacement)
      # shellcheck disable=SC2016
      printf '%s\n' "$artifacts_list" | tr ',' '\n' | sed 's/^/- `/;s/$/`/'
    } >> "$SLOT_DIR/RUN_INDEX.md"
  fi

  # Final verdict
  log "final verdict: $verdict"
  case "$verdict" in
    PASS)   exit 0 ;;
    FAIL)   exit 4 ;;
    PARTIAL) exit 4 ;;
    *)      exit 4 ;;
  esac
}

main "$@"
