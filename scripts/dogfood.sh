#!/usr/bin/env bash
# Dogfooding (docs/v2/45 §5): ArchSkillKit analizando ArchSkillKit con su
# propio runtime y sus propias reglas — el producto vigila su arquitectura.

set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
ART="$ROOT/artifacts/dogfood/$RUN_ID"
mkdir -p "$ART"

cd "$ROOT"
echo "== dogfood: ArchSkillKit sobre sí mismo =="

# 1) escanear el propio repo con el runtime pineado (mise)
ASTGREP="$(mise exec -C skills/architecture-discovery/runtime -- which ast-grep)"
SEMGREP="$(mise exec -C skills/architecture-discovery/runtime -- which semgrep)"
[ -x "$ASTGREP" ] && [ -x "$SEMGREP" ] || {
  echo "ERROR: runtime no instalado (mise run bootstrap)"; exit 2; }
"$ASTGREP" scan -c "$ROOT/skills/architecture-discovery/rules/ast-grep/sgconfig.yml" \
  --json=stream "$ROOT" > /tmp/dogfood-astgrep.jsonl 2>/dev/null
"$SEMGREP" scan --config "$ROOT/skills/architecture-discovery/rules/semgrep" \
  --json --metrics=off --no-rewrite-rule-ids "$ROOT" \
  > /tmp/dogfood-semgrep.json 2>/dev/null || true
echo "scanner evidence: $(grep -c . /tmp/dogfood-astgrep.jsonl) outline records"

# 2) pipeline V2 sobre el propio repositorio (entorno dev bloqueado)
cd python
uv run --locked python -m archskillkit init --repo "$ROOT" > "$ART/init.json"
uv run --locked python -m archskillkit ingest-code --repo "$ROOT" \
  --astgrep /tmp/dogfood-astgrep.jsonl --semgrep /tmp/dogfood-semgrep.json \
  --run-id "dogfood-$RUN_ID" > "$ART/ingest.json"
uv run --locked python -m archskillkit index-stats --repo "$ROOT" \
  > "$ART/index-stats.json"
uv run --locked python -m archskillkit discover --repo "$ROOT" \
  --run-id "dogfood-$RUN_ID" > "$ART/discover.json"
uv run --locked python -m archskillkit drift --repo "$ROOT" \
  > "$ART/drift.json"

files=$(jq -r .files "$ART/index-stats.json")
symbols=$(jq -r .symbols "$ART/index-stats.json")
echo "ingestado: $files ficheros, $symbols símbolos"
jq -e ".files > 0 and .symbols > 0" "$ART/index-stats.json" >/dev/null

echo "== dogfood OK — evidencia en $ART =="
