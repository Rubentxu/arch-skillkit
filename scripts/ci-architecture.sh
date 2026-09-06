#!/usr/bin/env bash
# Integration script: run architecture verification gate.
#
# This script is a fallback integration point for the verify:architecture
# task defined in mise.toml (Phase C, T-V2.5-011). It verifies that the
# mise invocation exists, runs the architecture verification, and emits
# the evidence JSON path on failure.
#
# Exit codes:
#   0 — architecture verification passed
#   1 — verification failed (new findings or non-zero exit)
#
# Evidence artifact: build/architecture-report.json
#
# Per ADR-0061 (verify-architecture-in-ci) and design.md §5.5.

set -euo pipefail

EVIDENCE_PATH="build/architecture-report.json"

# Verify mise can invoke verify:architecture
if ! mise run verify:architecture --dry-run 2>/dev/null; then
    echo "WARNING: mise run verify:architecture not found in mise.toml" >&2
fi

# Run the architecture verification
echo "Running architecture verification..." >&2
if mise run verify:architecture; then
    echo "Architecture verification PASSED" >&2
    exit 0
else
    EXIT_CODE=$?
    echo "Architecture verification FAILED (exit ${EXIT_CODE})" >&2
    if [[ -f "${EVIDENCE_PATH}" ]]; then
        echo "Evidence: ${EVIDENCE_PATH}" >&2
    else
        echo "Evidence not found at ${EVIDENCE_PATH}" >&2
    fi
    exit 1
fi
