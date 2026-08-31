#!/usr/bin/env bash
# Keeps MANIFEST.md in sync with the documentation tree.
#
# Scope: every file under docs/, skills/ and examples/, plus the root
# Markdown files (README.md, README.es.md, MANIFEST.md, LICENSE.es.md).
set -euo pipefail
cd "$(dirname "$0")/.."

manifest="MANIFEST.md"
fail=0

listed="$(sed -n 's/^- `\(.*\)`$/\1/p' "$manifest" | sort)"

while IFS= read -r path; do
  [ -z "$path" ] && continue
  if [ ! -f "$path" ]; then
    echo "ERROR: listed in $manifest but missing on disk: $path"
    fail=1
  fi
done <<< "$listed"

actual="$(
  {
    find docs skills examples -type f
    printf '%s\n' README.md README.es.md MANIFEST.md LICENSE.es.md
  } | sort
)"

unlisted="$(comm -13 <(printf '%s\n' "$listed") <(printf '%s\n' "$actual") || true)"
if [ -n "$unlisted" ]; then
  echo "ERROR: present on disk but not listed in $manifest:"
  echo "$unlisted"
  fail=1
fi

if [ "$fail" -eq 0 ]; then
  echo "OK: $manifest is in sync with the documentation tree."
fi
exit "$fail"
