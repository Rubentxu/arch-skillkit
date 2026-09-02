#!/usr/bin/env bash
# Quick visualization of Real-OSS validation artifacts.
#
# Usage:
#   scripts/oss/view.sh <name> [command]
#
#   <name>   project run name as passed to run-oss.sh (e.g. nextjs).
#            Resolves to the newest artifacts/oss/<name>-*/ directory.
#   command  one of:
#     serve    (default) interactive LikeC4 UI on localhost
#     png      open the rendered PNG with the desktop viewer
#     info     print the run report (report.md) + evidence summary
#     open     open the artifacts folder in the file manager
#
# External-viewer cheat sheet (printed by `info`):
#   arrows.arrows   → https://arrows.app      (Import → File)
#   drawio.drawio   → https://app.diagrams.net (File → Open from device)
#   canvas.json     → Obsidian / any JSON Canvas viewer
#   graphml.graphml → Cytoscape / Gephi / yEd

set -euo pipefail

NAME="${1:?usage: view.sh <name> [serve|png|info|open]}"
CMD="${2:-serve}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

RUN_DIR="$(ls -d "$ROOT"/artifacts/oss/"$NAME"-* 2>/dev/null | sort | tail -1)"
[ -n "$RUN_DIR" ] || { echo "error: no artifacts/oss/$NAME-* run found" >&2; exit 1; }
echo "run: $RUN_DIR"

LIKEC4_BIN="$(ls "$HOME"/.local/share/mise/installs/npm-likec4/*/node_modules/.bin/likec4 2>/dev/null | tail -1 || true)"

case "$CMD" in
  serve)
    [ -n "$LIKEC4_BIN" ] || { echo "error: likec4 not found (mise bootstrap)" >&2; exit 1; }
    [ -f "$RUN_DIR/project/likec4.c4" ] || { echo "error: no likec4.c4 in $RUN_DIR/project" >&2; exit 1; }
    # LIKEC4_WORKSPACE pins the workspace root: the CLI anchors on CWD
    # otherwise and would scan the whole host repo.
    echo "starting LikeC4 UI — open the printed http://localhost:5173"
    LIKEC4_WORKSPACE="$RUN_DIR/project" exec "$LIKEC4_BIN" start "$RUN_DIR/project"
    ;;
  png)
    PNG="$(ls "$RUN_DIR"/render/*.png 2>/dev/null | tail -1 || true)"
    [ -n "$PNG" ] || { echo "error: no PNG rendered for this run" >&2; exit 1; }
    xdg-open "$PNG"
    ;;
  info)
    cat "$RUN_DIR/report.md" 2>/dev/null || true
    echo
    echo "evidence (sha256 manifest): $RUN_DIR/evidence/manifest.txt"
    echo "projections:   $RUN_DIR/project/"
    echo "render:        $RUN_DIR/render/"
    echo "step logs:     $RUN_DIR/runs/"
    ;;
  open)
    xdg-open "$RUN_DIR"
    ;;
  *)
    echo "error: unknown command '$CMD' (serve|png|info|open)" >&2
    exit 1
    ;;
esac
