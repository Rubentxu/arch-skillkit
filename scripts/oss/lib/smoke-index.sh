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
cat > "$SLOT_DIR/RUN_MANIFEST.yaml" <<'YAMLEOF'
# RUN_MANIFEST.yaml — slot run manifest
# Populated by smoke-oss.sh after slot execution
slot: SLOT_PLACEHOLDER
name: NAME_PLACEHOLDER
date_stamp: DATE_PLACEHOLDER
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
head_before: ""
head_after: ""
likec4_validate: ""
scan_ast_grep: ""
verdict: ""
content_quality_audit: false
evidence_sha256_manifest: ""
artifacts: []
cleanup_audit: false
YAMLEOF

sed -i "s|SLOT_PLACEHOLDER|$SLOT_ID|g" "$SLOT_DIR/RUN_MANIFEST.yaml"
sed -i "s|DATE_PLACEHOLDER|$DATE_STAMP|g" "$SLOT_DIR/RUN_MANIFEST.yaml"

# Stub evidence/manifest.txt
> "$EVIDENCE_DIR/manifest.txt"

printf '[smoke-index] created slot structure at %s\n' "$SLOT_DIR"
