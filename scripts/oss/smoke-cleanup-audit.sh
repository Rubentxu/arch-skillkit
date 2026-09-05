#!/usr/bin/env bash
# Cleanup audit: verifies zero ark-smoke residue across 3 checks.
#
# Checks:
#   1. podman ps -a --filter name=ark-smoke-* → must be empty
#   2. find /tmp -maxdepth 1 -name 'ark-smoke-*' -type d → must be empty
#   3. pgrep -f ark-smoke → must return no PIDs
#
# Usage:
#   smoke-cleanup-audit.sh [--json]
#
# Exit codes:
#   0 = all checks pass (zero residue)
#   1 = one or more checks found residue
#
# With --json: outputs machine-readable JSON with per-check results.

set -euo pipefail

MODE="${1:-human}"
[ "$MODE" = "--json" ] && JSON=true || JSON=false

CHECKS_FAILED=0

# Check 1: podman containers
PODMAN_RESULT=$(podman ps -a --filter 'name=ark-smoke-*' --format '{{.Names}}' 2>/dev/null || echo "ERROR")
if [ "$PODMAN_RESULT" = "ERROR" ]; then
  PODMAN_STATUS="error"
  PODMAN_OUTPUT="podman command failed"
  CHECKS_FAILED=1
elif [ -z "$PODMAN_RESULT" ]; then
  PODMAN_STATUS="pass"
  PODMAN_OUTPUT="no ark-smoke-* containers"
else
  PODMAN_STATUS="fail"
  PODMAN_OUTPUT="$PODMAN_RESULT"
  CHECKS_FAILED=1
fi

# Check 2: /tmp directories
TMP_RESULT=$(find /tmp -maxdepth 1 -name 'ark-smoke-*' -type d 2>/dev/null || echo "ERROR")
if [ "$TMP_RESULT" = "ERROR" ]; then
  TMP_STATUS="error"
  TMP_OUTPUT="find command failed"
  CHECKS_FAILED=1
elif [ -z "$TMP_RESULT" ]; then
  TMP_STATUS="pass"
  TMP_OUTPUT="no ark-smoke-* directories in /tmp"
else
  TMP_STATUS="fail"
  TMP_OUTPUT="$TMP_RESULT"
  CHECKS_FAILED=1
fi

# Check 3: processes
# pgrep returns: 0 = found matches, 1 = no matches, 2+ = error
PGREP_EXIT=0
PGREP_OUTPUT=$(pgrep -f 'ark-smoke' 2>/dev/null) || PGREP_EXIT=$?
if [ $PGREP_EXIT -ge 2 ]; then
  PGREP_STATUS="error"
  PGREP_OUTPUT="pgrep command failed (exit $PGREP_EXIT)"
  CHECKS_FAILED=1
elif [ -z "$PGREP_OUTPUT" ]; then
  PGREP_STATUS="pass"
  PGREP_OUTPUT="no ark-smoke processes"
else
  PGREP_STATUS="fail"
  PGREP_OUTPUT="PIDs: $PGREP_OUTPUT"
  CHECKS_FAILED=1
fi

if $JSON; then
  # shellcheck disable=SC2016
  printf '{"cleanup_audit":{"podman":{"status":"%s","output":"%s"},"tmp_dirs":{"status":"%s","output":"%s"},"processes":{"status":"%s","output":"%s"},"overall":"%s"}}\n' \
    "$PODMAN_STATUS" "$PODMAN_OUTPUT" \
    "$TMP_STATUS" "$TMP_OUTPUT" \
    "$PGREP_STATUS" "$PGREP_OUTPUT" \
    "$([ $CHECKS_FAILED -eq 0 ] && echo "pass" || echo "fail")"
else
  printf '[cleanup-audit] podman containers: %s — %s\n' "$PODMAN_STATUS" "$PODMAN_OUTPUT"
  printf '[cleanup-audit] /tmp ark-smoke dirs: %s — %s\n' "$TMP_STATUS" "$TMP_OUTPUT"
  printf '[cleanup-audit] ark-smoke processes: %s — %s\n' "$PGREP_STATUS" "$PGREP_OUTPUT"
  if [ $CHECKS_FAILED -eq 0 ]; then
    printf '[cleanup-audit] RESULT: PASS — zero residue\n'
  else
    printf '[cleanup-audit] RESULT: FAIL — residue detected\n'
  fi
fi

exit $CHECKS_FAILED
