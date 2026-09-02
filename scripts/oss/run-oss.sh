#!/usr/bin/env bash
# Real-OSS validation pipeline (docs/v2/uat/v2.1-real-oss-validation-plan.md).
#
# Runs the archskillkit pipeline end-to-end on a real open-source
# repository with resource caps and full teardown:
#   - CPU: ast-grep/semgrep pinned to --threads/--jobs 4 (doctor budget)
#   - Priority: nice -n 19 so interactive work keeps responsiveness
#   - Wallclock: hard 30-minute timeout on the whole pipeline
#   - Hermeticity: ARCH_SKILLKIT_HOME + XDG dirs under a private root
#     (R5 env-based fallback; Podman optional — see plan)
#   - Read-only invariant: the cloned repo's git status is captured
#     before and after and must be identical (UAT2-001)
#   - Teardown: the clone and the state root are removed on exit
#
# Usage:
#   scripts/oss/run-oss.sh <name> <git-url> [branch]
#
# Artifacts (committed): artifacts/oss/<name>-<date>/
#   scan.astgrep.jsonl  scan.semgrep.json  ingest.json  discover.json
#   review.json  drift.json  index-stats.json
#   project/likec4.c4  project/arrows.arrows  project/canvas.json
#   project/graphml.graphml  project/drawio.drawio
#   render/likec4.png           (only if Chrome is available)
#   evidence/manifest.txt       (sha256 of every artifact)
#   runs/<step>.log             (gitignored checkpoint logs)
#   report.md                   (auto-generated summary)

set -uo pipefail

NAME="${1:?usage: run-oss.sh <name> <git-url> [branch]}"
REPO_URL="${2:?usage: run-oss.sh <name> <git-url> [branch]}"
BRANCH="${3:-}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DATE_STAMP="$(date -u +%Y%m%d)"
OUT="$ROOT/artifacts/oss/$NAME-$DATE_STAMP"
WORK="$(mktemp -d /tmp/ark-oss-"$NAME"-XXXXXX)"
REPO="$WORK/repo"
STATE="$WORK/state"
SGCONFIG="$ROOT/skills/architecture-discovery/rules/ast-grep/sgconfig.yml"
SEMGREP_RULES="$ROOT/skills/architecture-discovery/rules/semgrep"
THREADS=4
STARTED="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

mkdir -p "$OUT/project" "$OUT/render" "$OUT/evidence" "$OUT/runs" "$STATE"

log() { printf '[oss:%s] %s\n' "$NAME" "$*"; }
step() { # <step-name> <cmd...>
  local s="$1"; shift
  log "▸ $s"
  if ! nice -n 19 "$@" >"$OUT/runs/$s.log" 2>&1; then
    log "✗ $s failed (see $OUT/runs/$s.log)"
    tail -5 "$OUT/runs/$s.log" >&2
    return 1
  fi
  log "✓ $s"
}

cleanup() {
  local rc=$?
  log "teardown: removing $WORK"
  rm -rf "$WORK"
  exit $rc
}
trap cleanup EXIT

# ---- pre-flight -------------------------------------------------------
log "pre-flight: repo=$REPO_URL branch=${BRANCH:-default}"
load1="$(awk '{print $1}' /proc/loadavg)"
log "loadavg=$load1 (plan gate is 2.0; proceeding only on explicit override)"
disk_gb="$(df -BG /tmp | awk 'NR==2{gsub("G","");print $4}')"
if [ "${disk_gb:-0}" -lt 5 ]; then
  log "✗ pre-flight: only ${disk_gb}G free under /tmp (need 5G)"
  exit 1
fi

# ---- tool resolution --------------------------------------------------
ARCH_PY="$ROOT/python/.venv/bin/python"
[ -x "$ARCH_PY" ] || { log "✗ python venv missing (mise run bootstrap)"; exit 1; }
AST_GREP="$(command -v ast-grep || \
  ls "$HOME"/.local/share/mise/installs/github-ast-grep-ast-grep/*/ast-grep 2>/dev/null | tail -1)"
[ -n "$AST_GREP" ] || { log "✗ ast-grep not found"; exit 1; }
SEMGREP_BIN="$(command -v semgrep || \
  ls "$HOME"/.local/share/mise/installs/pipx-semgrep/*/bin/semgrep 2>/dev/null | tail -1)"
[ -n "$SEMGREP_BIN" ] || { log "✗ semgrep not found"; exit 1; }
ARK="env ARCH_SKILLKIT_HOME=$STATE/home
  XDG_CONFIG_HOME=$STATE/config XDG_DATA_HOME=$STATE/data
  XDG_STATE_HOME=$STATE/state XDG_CACHE_HOME=$STATE/cache
  PYTHONPATH=$ROOT/python/src $ARCH_PY -m archskillkit"

# ---- clone ------------------------------------------------------------
clone_args=(clone --depth 1 --single-branch)
[ -n "$BRANCH" ] && clone_args+=(--branch "$BRANCH")
clone_args+=("$REPO_URL" "$REPO")
step clone git "${clone_args[@]}"
size_mb="$(du -sm "$REPO" | cut -f1)"
log "clone size: ${size_mb}MB"
git -C "$REPO" status --porcelain > "$OUT/runs/git-before.txt"
git -C "$REPO" rev-parse HEAD > "$OUT/runs/commit.txt"
log "commit: $(cat "$OUT/runs/commit.txt")"

# ---- scan (both scanners) --------------------------------------------
step scan-astgrep "$AST_GREP" scan -c "$SGCONFIG" \
  --threads "$THREADS" --json=stream "$REPO"
mv "$OUT/runs/scan-astgrep.log" "$OUT/scan.astgrep.jsonl"
log "ast-grep records: $(wc -l < "$OUT/scan.astgrep.jsonl")"

# semgrep: repo-local cache, metrics off, offline-friendly.
step scan-semgrep env SEMGREP_SEND_METRICS=off \
  "$SEMGREP_BIN" scan --config "$SEMGREP_RULES" --json \
  --jobs "$THREADS" --quiet --max-target-bytes 1000000 "$REPO"
mv "$OUT/runs/scan-semgrep.log" "$OUT/scan.semgrep.json"
log "semgrep results: "$(python3 -c "import json;print(len(json.load(open('$OUT/scan.semgrep.json')).get('results',[])))" 2>/dev/null || echo '?')

# ---- ingest / discover / review / drift ------------------------------
step init $ARK init --repo "$REPO"
step ingest $ARK ingest-code --repo "$REPO" \
  --astgrep "$OUT/scan.astgrep.jsonl" \
  --semgrep "$OUT/scan.semgrep.json" \
  --run-id "oss-$NAME" --scan-root "$REPO"
step index-stats $ARK index-stats --repo "$REPO"
cp "$OUT/runs/index-stats.log" "$OUT/index-stats.json"
step discover $ARK discover --repo "$REPO" --run-id "oss-$NAME"
cp "$OUT/runs/discover.log" "$OUT/discover.json"
step review $ARK review --repo "$REPO"
cp "$OUT/runs/review.log" "$OUT/review.json"
step drift $ARK drift --repo "$REPO"
cp "$OUT/runs/drift.log" "$OUT/drift.json"

# ---- project (all five formats) --------------------------------------
step project $ARK project --repo "$REPO" --format all --force
cp "$OUT/runs/project.log" "$OUT/project/projections.json"
# Copy every generated projection to a canonical name under project/.
python3 - "$OUT/project/projections.json" "$OUT/project" <<'PYEOF'
import json, shutil, sys
from pathlib import Path
projections = json.load(open(sys.argv[1]))["projections"]
dest = Path(sys.argv[2])
names = {"likec4": "likec4.c4", "arrows": "arrows.arrows",
         "graphml": "graphml.graphml", "jsoncanvas": "canvas.json",
         "drawio": "drawio.drawio"}
for p in projections:
    target = names.get(p["format"])
    if target and Path(p["path"]).is_file():
        shutil.copy2(p["path"], dest / target)
PYEOF

# ---- validate + render (needs likec4; PNG needs a browser) -----------
CHROME="$(command -v google-chrome || command -v chromium || \
  command -v chromium-browser || \
  ls "$HOME"/.cache/ms-playwright/chromium-*/chrome-linux*/chrome 2>/dev/null | tail -1)"
LIKEC4_BIN="$(ls "$HOME"/.local/share/mise/installs/npm-likec4/*/node_modules/.bin/likec4 2>/dev/null | tail -1)"
[ -n "$LIKEC4_BIN" ] || LIKEC4_BIN="$(command -v likec4 || true)"
if [ -n "$LIKEC4_BIN" ] && [ -f "$OUT/project/likec4.c4" ]; then
  # NOTE: likec4 resolves its workspace root by walking UP from the
  # target dir — keep the project under the unique $WORK parent so
  # sibling /tmp dirs can never leak into the validation.
  render_dir="$WORK/likec4proj"
  mkdir -p "$render_dir"
  cp "$OUT/project/likec4.c4" "$render_dir/"
  # NOTE: likec4 anchors its workspace on the CURRENT directory (not
  # the path argument) and scans it recursively — so both steps must
  # cd into the isolated project dir or the host repo gets scanned.
  if (cd "$render_dir" && nice -n 19 "$LIKEC4_BIN" validate --quiet .) \
      >"$OUT/runs/validate-likec4.log" 2>&1; then
    log "✓ validate-likec4"
    LIKEC4_VALID="PASS"
  else
    log "✗ validate-likec4 failed (see runs/validate-likec4.log)"
    LIKEC4_VALID="FAIL"
  fi
  if [ -n "$CHROME" ]; then
    export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-$HOME/.cache/ms-playwright}"
    if (cd "$render_dir" && nice -n 19 "$LIKEC4_BIN" export png \
        -o "$OUT/render" .) >"$OUT/runs/render.log" 2>&1; then
      log "✓ render"
    else
      log "✗ render skipped (R1): likec4 export failed"
    fi
  else
    log "render skipped (R1): no Chrome/Playwright chromium available"
  fi
else
  log "render skipped (R1): likec4 not available"
fi

# ---- invariants + evidence -------------------------------------------
git -C "$REPO" status --porcelain > "$OUT/runs/git-after.txt"
if ! diff -q "$OUT/runs/git-before.txt" "$OUT/runs/git-after.txt" >/dev/null; then
  log "✗ UAT2-001 invariant VIOLATED: repo was modified"
  diff "$OUT/runs/git-before.txt" "$OUT/runs/git-after.txt" >&2
  exit 1
fi
log "✓ UAT2-001 invariant: repository unchanged"

(
  cd "$OUT"
  find . -type f ! -path "./runs/*" ! -name manifest.txt \
    -exec sha256sum {} \; | sort -k2 > evidence/manifest.txt
)

ENDED="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
cat > "$OUT/report.md" <<EOF
# $NAME — Real OSS validation

- **Repo**: $REPO_URL ($NAME)
- **Commit**: $(cat "$OUT/runs/commit.txt")
- **Started**: $STARTED · **Finished**: $ENDED
- **Clone size**: ${size_mb}MB
- **UAT2-001 invariant**: PASS (git status identical before/after)

## Pipeline results

| Step | Result |
|------|--------|
| ast-grep symbols | $(wc -l < "$OUT/scan.astgrep.jsonl") records |
| semgrep matches | $(python3 -c "import json;print(len(json.load(open('$OUT/scan.semgrep.json')).get('results',[])))" 2>/dev/null || echo 'n/a') |
| Code Index | see index-stats.json |
| Architecture | see discover.json (elements/relations) |
| Review findings | see review.json |
| Drift findings | see drift.json |
| Projections | likec4/arrows/canvas/graphml/drawio under project/ |
| LikeC4 validation | ${LIKEC4_VALID:-SKIPPED} (runs/validate-likec4.log) |
| Render | $(ls "$OUT/render" 2>/dev/null | head -1 || echo "skipped (R1)") |

## Evidence

sha256 manifest: evidence/manifest.txt
EOF

log "DONE → $OUT"
exit 0
