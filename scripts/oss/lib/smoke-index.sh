#!/usr/bin/env bash
# Creates per-slot artifact directories and emits slot-level INDEX/MANIFEST files.
# Per-slot layout: $STABLE_ROOT/<slot>/<date>/{RUN_INDEX.md, RUN_MANIFEST.yaml, evidence/manifest.txt}
#
# Usage:
#   smoke-index.sh <stable_root> <slot_id> <date_stamp>
#
# Creates directories and empty stub files. Consumers populate them after each step.
# Exit: 0 on success, 1 on missing arg or mkdir failure.

set -euo pipefail

STABLE_ROOT="${1:?usage: smoke-index.sh <stable_root> <slot_id> <date_stamp>}"
SLOT_ID="${2:?}"
DATE_STAMP="${3:-$(date -u +%Y%m%d)}"

SLOT_DIR="$STABLE_ROOT/$SLOT_ID/$DATE_STAMP"
EVIDENCE_DIR="$SLOT_DIR/evidence"

mkdir -p "$EVIDENCE_DIR"

# Stub RUN_INDEX.md with structure (content added by smoke-oss.sh after slot run)
# Frontmatter block added by smoke-oss.sh after sed population (ACT-3)
cat > "$SLOT_DIR/RUN_INDEX.md" <<'INDEXEOF'
# Slot Run Index

## Run Metadata

| Field | Value |
|-------|-------|
| Slot | SLOT_PLACEHOLDER |
| Date | DATE_PLACEHOLDER |
| Repo | REPO_PLACEHOLDER |
| Pinned SHA | PINNED_SHA_PLACEHOLDER |
| Clone size (MB) | CLONE_SIZE_PLACEHOLDER |
| Started | STARTED_PLACEHOLDER |
| Ended | ENDED_PLACEHOLDER |
| Wallclock (s) | WALLCLOCK_PLACEHOLDER |
| Verdict | VERDICT_PLACEHOLDER |

## Checklist

- [ ] command_exit: present
- [ ] prose_present: present
- [ ] sha_bound: verified

INDEXEOF

# Replace placeholders with actual values
sed -i "s|SLOT_PLACEHOLDER|$SLOT_ID|g" "$SLOT_DIR/RUN_INDEX.md"
sed -i "s|DATE_PLACEHOLDER|$DATE_STAMP|g" "$SLOT_DIR/RUN_INDEX.md"

  # Stub RUN_MANIFEST.yaml (content added by smoke-oss.sh)
  # Frontmatter keys (ACT-3): YAML comment block at top
  # ACT-5: head_before/head_after renamed to git_status_before/git_status_after
  # ACT-5: added head_commit_before/head_commit_after fields
cat > "$SLOT_DIR/RUN_MANIFEST.yaml" <<'YAMLEOF'
# RUN_MANIFEST.yaml — slot run manifest
# Populated by smoke-oss.sh after slot execution
# --- YAML frontmatter (ACT-3: REQ-OSS-SMOKE-SHABinding) ---
# pinned_sha: PINNED_SHA_PLACEHOLDER
# pin_source: PIN_SOURCE_PLACEHOLDER
# campaign_id: CAMPAIGN_ID_PLACEHOLDER
# slot_id: SLOT_PLACEHOLDER
# run_date: RUN_DATE_PLACEHOLDER
slot: SLOT_PLACEHOLDER
name: NAME_PLACEHOLDER
date_stamp: DATE_STAMP_PLACEHOLDER
repo_url: REPO_PLACEHOLDER
pinned_sha: PINNED_SHA_PLACEHOLDER
pin_source: PIN_SOURCE_PLACEHOLDER
cloned_sha: ""
pin_match: false
clone_size_mb: 0
started: ""
ended: ""
wallclock_seconds: 0
uat2_001: false
git_status_before: ""
git_status_after: ""
head_commit_before: ""
head_commit_after: ""
likec4_validate: ""
scan_ast_grep: ""
verdict: ""
content_quality_audit: false
evidence_sha256_manifest: ""
artifacts: []
cleanup_audit: false
YAMLEOF

  sed -i \
  -e "s|SLOT_PLACEHOLDER|$SLOT_ID|g" \
  -e "s|RUN_DATE_PLACEHOLDER|RUN_DATE_PLACEHOLDER|g" \
  -e "s|DATE_STAMP_PLACEHOLDER|$DATE_STAMP|g" \
  -e "s|CAMPAIGN_ID_PLACEHOLDER|CAMPAIGN_ID_PLACEHOLDER|g" \
  -e "s|PINNED_SHA_PLACEHOLDER|PINNED_SHA_PLACEHOLDER|g" \
  -e "s|PIN_SOURCE_PLACEHOLDER|PIN_SOURCE_PLACEHOLDER|g" \
  "$SLOT_DIR/RUN_MANIFEST.yaml"

# Stub evidence/manifest.txt (populated after doc finalization — ACT-1/2)
true > "$EVIDENCE_DIR/manifest.txt"

printf '[smoke-index] created slot structure at %s\n' "$SLOT_DIR"
