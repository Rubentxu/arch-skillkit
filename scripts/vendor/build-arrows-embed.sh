#!/usr/bin/env bash
# Build the Arrows.app embed bundle (V2.4 M5 slice 26).
#
# Builds neo4j-labs/arrows.app with BUILD_EMBED=1 and copies the
# dist output into the vendor directory under the data root.
#
# The resulting embed.html has its <base href="/"> rewritten to "./"
# so it works correctly when served from a sub-path (e.g. /vendor/arrows/).
#
# Usage:
#   scripts/vendor/build-arrows-embed.sh [VENDOR_DIR]
#
#   VENDOR_DIR defaults to ~/.local/share/arch-skillkit/vendor/arrows
#   (the canonical arch_data_root() location).
#
# The script is manual-only: it never runs automatically as part of
# any build or CI pipeline. Re-run after neo4j-labs/arrows.app updates.
#
# Prerequisites:
#   - git
#   - node >= 18
#   - npm ci access (no auth required for public repo)
#
# Apache-2.0 license applies to the arrows.app output.

set -euo pipefail

# Canonical data-root default
DATA_ROOT="${DATA_ROOT:-${XDG_DATA_HOME:-$HOME/.local/share}/arch-skillkit}"
VENDOR_DIR="${1:-$DATA_ROOT/vendor/arrows}"

REPO_DIR="$(mktemp -d)"
trap 'rm -rf "$REPO_DIR"' EXIT

echo "=== Building Arrows.app embed bundle ==="
echo "Source:  https://github.com/neo4j-labs/arrows.app"
echo "Vendor:  $VENDOR_DIR"
echo ""

# Clone and build
git clone --depth=1 https://github.com/neo4j-labs/arrows.app "$REPO_DIR/arrows.app"
cd "$REPO_DIR/arrows.app"
npm ci
BUILD_EMBED=1 npx nx build arrows-ts --skip-nx-cache

# Locate dist
DIST_DIR="$REPO_DIR/arrows.app/dist/apps/arrows/www"
if [[ ! -d "$DIST_DIR" ]]; then
  echo "ERROR: build did not produce $DIST_DIR" >&2
  exit 1
fi

# Rewrite <base href="/"> -> <base href="./"> in embed.html
EMBED_HTML="$DIST_DIR/embed.html"
if [[ -f "$EMBED_HTML" ]]; then
  sed -i 's|<base href="/">|<base href="./">|g' "$EMBED_HTML"
  echo "Rewrote <base href> in embed.html"
fi

# Install into vendor dir
mkdir -p "$VENDOR_DIR"
cp -r "$DIST_DIR/"* "$VENDOR_DIR/"
echo ""
echo "=== Bundle installed to $VENDOR_DIR ==="
echo "Files:"
ls -la "$VENDOR_DIR/"
echo ""
echo "Done. To serve: point your HTTP server at $VENDOR_DIR"
