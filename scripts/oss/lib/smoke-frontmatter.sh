#!/usr/bin/env bash
# Emits per-doc YAML frontmatter (first 10 lines) for smoke run documents.
# Keys: pinned_sha, pin_source, campaign_id, slot_id, run_date
#
# Usage:
#   smoke-frontmatter.sh <output_path> <pinned_sha> <pin_source> <campaign_id> <slot_id>
#
# Output: writes frontmatter to <output_path>, overwriting if exists.
# Exit: 0 on success, 1 on missing argument.

set -euo pipefail

OUTPUT="${1:?usage: smoke-frontmatter.sh <output> <pinned_sha> <pin_source> <campaign_id> <slot_id>}"
PINNED_SHA="${2:?}"
PIN_SOURCE="${3:?}"
CAMPAIGN_ID="${4:?}"
SLOT_ID="${5:?}"
RUN_DATE="$(date -u +%Y-%m-%d)"

{
  printf -- '# --- smoke run frontmatter (DO NOT EDIT MANUALLY) ---\n'
  printf 'pinned_sha: %s\n' "$PINNED_SHA"
  printf 'pin_source: %s\n' "$PIN_SOURCE"
  printf 'campaign_id: %s\n' "$CAMPAIGN_ID"
  printf 'slot_id: %s\n' "$SLOT_ID"
  printf 'run_date: %s\n' "$RUN_DATE"
  printf -- '# ---------------------------------------------------\n'
} > "$OUTPUT"
