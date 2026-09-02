#!/usr/bin/env bash
# Fase 2 (docs/v2/24-distribution-and-installation.md) — verificación de
# instalación del release en contenedores limpios, EN LOCAL (sin cuota de
# GitHub). Dos contenedores Debian vacíos:
#
#   A (con red):   instala el wheel del release como un usuario, setup,
#                  doctor=ready, analiza un repo de prueba, corrompe un
#                  byte (debe detectarse) y deja las cachés preparadas.
#   B (sin red):   instala el wheel offline desde las cachés compartidas,
#                  setup --offline, doctor=ready.
#
# Evidencia: artifacts/verify/<RUN_ID>/
#
# Uso: scripts/verify/run-verify.sh [VERSION]        (por defecto: 0.3.0)
#      WHEEL_LOCAL=dist/archskillkit-0.3.0-py3-none-any.whl \
#        scripts/verify/run-verify.sh 0.3.0                # wheel local

set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VERSION="${1:-0.3.0}"
IMAGE="${VERIFY_IMAGE:-debian:bookworm-slim}"
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
ART="$ROOT/artifacts/verify/$RUN_ID"
NAME_A="ark-verify-$RUN_ID-a"
NAME_B="ark-verify-$RUN_ID-b"
V_SHARE="ark-$RUN_ID-share"
V_UVCACHE="ark-$RUN_ID-uvcache"
V_ASKCACHE="ark-$RUN_ID-askcache"
V_DATA="ark-$RUN_ID-data"
V_STATE="ark-$RUN_ID-state"
WHEEL_URL="https://github.com/Rubentxu/arch-skillkit/releases/download/v$VERSION/archskillkit-$VERSION-py3-none-any.whl"
WHEEL_LOCAL="${WHEEL_LOCAL:-}"

mkdir -p "$ART"

cleanup() {
  local code=$?
  podman rm -f "$NAME_A" "$NAME_B" >/dev/null 2>&1 || true
  podman volume rm "$V_SHARE" "$V_UVCACHE" "$V_ASKCACHE" "$V_DATA" "$V_STATE" \
    >/dev/null 2>&1 || true
  if [ "$code" -ne 0 ]; then
    echo "FALLO — evidencia en $ART" >&2
  fi
  exit "$code"
}
trap cleanup EXIT INT TERM

echo "== Verificación de release v$VERSION (run $RUN_ID) =="
echo "evidencia: $ART"

podman volume create "$V_SHARE" >/dev/null
podman volume create "$V_UVCACHE" >/dev/null
podman volume create "$V_ASKCACHE" >/dev/null
podman volume create "$V_DATA" >/dev/null
podman volume create "$V_STATE" >/dev/null

# ---------------------------------------------------------------------------
# Contenedor A — camino online completo
# ---------------------------------------------------------------------------
echo "-- A: contenedor limpio (sin python, sin git, sin herramientas)"
podman run -d --name "$NAME_A" \
  -v "$V_SHARE":/share -v "$V_UVCACHE":/root/.cache/uv \
  -v "$V_ASKCACHE":/root/.cache/arch-skillkit \
  -v "$V_DATA":/root/.local/share \
  -v "$V_STATE":/root/.local/state \
  -v "$ROOT/skills/architecture-discovery/rules":/opt/rules:ro,Z \
  "$IMAGE" sleep infinity >/dev/null
if [ -n "$WHEEL_LOCAL" ]; then
  podman cp "$WHEEL_LOCAL" "$NAME_A":/tmp/wheel.whl
  WHEEL_REF="/tmp/wheel.whl"
else
  WHEEL_REF="$WHEEL_URL"
fi

echo "-- A: bootstrap del instalador (curl) + uv + wheel del release"
podman exec -e WHEEL_REF="$WHEEL_REF" "$NAME_A" bash -Eeuo pipefail -c '
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq curl ca-certificates git jq >/dev/null
  curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null 2>&1
  export PATH="/root/.local/bin:$PATH"
  uv --version
  uv tool install --python 3.12 --extra attestation "$WHEEL_REF"
  cp /root/.local/bin/uv /share/uv
  archskillkit --help > /dev/null
  echo "CLI responde"
' | tee "$ART/install.log"

echo "-- A: setup (runtime descargado y verificado) + doctor ready"
podman exec "$NAME_A" bash -Eeuo pipefail -c '
  export PATH="/root/.local/bin:$PATH"
  archskillkit setup 2>&1
  archskillkit doctor > /share/doctor-online.json
  jq -e ".status == \"ready\"" /share/doctor-online.json >/dev/null
  echo "doctor: ready"
' | tee "$ART/doctor-online.log"

echo "-- A: análisis de repo de prueba (regla de oro: repo intacto)"
podman exec "$NAME_A" bash -Eeuo pipefail -c '
  { set -x
  export PATH="/root/.local/bin:$PATH"
  RT=$(echo "$HOME/.local/share/arch-skillkit/runtimes/"*/*/*)
  git config --global user.email "verify@test"
  git config --global user.name "verify"
  mkdir /fixture && cd /fixture
  git init -q
  git remote add origin https://github.com/rubentxu/verify-fixture.git
  mkdir -p src
  printf "fun process(input: String): String = input.trim()\n" > src/Main.kt
  git add -A && git commit -qm "fixture"
  before=$(git status --porcelain | wc -l)

  "$RT/ast-grep" scan -c /opt/rules/ast-grep/sgconfig.yml --json=stream . \
    > /tmp/astgrep.jsonl 2>/dev/null
  "$RT/semgrep-venv/bin/semgrep" scan --config /opt/rules/semgrep --json \
    --metrics=off --no-rewrite-rule-ids . > /tmp/semgrep.json 2>/dev/null

  archskillkit init --repo . >/dev/null
  archskillkit ingest-code --repo . --astgrep /tmp/astgrep.jsonl \
    --semgrep /tmp/semgrep.json --run-id verify >/dev/null
  archskillkit index-stats --repo . | jq -e ".files > 0" >/dev/null
  after=$(git status --porcelain | wc -l)
  [ "$before" = "$after" ] && [ "$after" = "0" ]
  echo "análisis OK — repo intacto"
  } > /tmp/analysis.log 2>&1
  rc=$?
  cat /tmp/analysis.log
  exit $rc
' | tee "$ART/analysis.log"

echo "-- A: test de corrupción (un byte alterado debe detectarse)"
cat > "$ART/corrupt.sh" <<'SCRIPT'
#!/usr/bin/env bash
set -Eeuo pipefail
export PATH="/root/.local/bin:$PATH"
BIN=$(ls "$HOME/.local/share/arch-skillkit/runtimes/"*/*/*/ast-grep)
echo "corruptiendo: $BIN"
printf "X" | dd of="$BIN" bs=1 seek=100 conv=notrunc 2>/dev/null
# el código 2 de doctor ES el contrato: corrupción detectada
archskillkit doctor > /tmp/doctor-corrupt.json || true
jq -e '.status == "corruption"' /tmp/doctor-corrupt.json >/dev/null
echo "corrupción detectada: OK"
SCRIPT
podman cp "$ART/corrupt.sh" "$NAME_A":/tmp/corrupt.sh
podman exec "$NAME_A" bash /tmp/corrupt.sh 2>&1 | tee "$ART/corruption.log"
podman cp "$NAME_A":/tmp/doctor-corrupt.json "$ART/doctor-corrupt.json"

echo "-- A: preparación del material air-gap (wheel + bundle + trust root)"
podman exec -e WHEEL_REF="$WHEEL_REF" -e VERSION="$VERSION" \
  -e RELEASE_BASE="https://github.com/Rubentxu/arch-skillkit/releases/download" \
  "$NAME_A" bash -Eeuo pipefail -c '
  export PATH="/root/.local/bin:$PATH"
  PT="$HOME/.local/share/uv/tools/archskillkit/bin/python"
  if [ -f /tmp/wheel.whl ]; then cp /tmp/wheel.whl /share/wheel.whl; else curl -LsS -o /share/wheel.whl "$WHEEL_REF"; fi
  DIGEST=$(sha256sum /share/wheel.whl | cut -d" " -f1)
  curl -sS -H "Accept: application/vnd.github+json" \
    "https://api.github.com/repos/Rubentxu/arch-skillkit/attestations/sha256:$DIGEST" \
    | jq -r ".attestations[0].bundle_url" > /tmp/bundle_url
  curl -LsS -o /tmp/bundle.snappy "$(cat /tmp/bundle_url)"
  "$PT" - <<PY
import cramjam
blob = open("/tmp/bundle.snappy", "rb").read()
clean = bytes(cramjam.snappy.decompress_raw(blob))
open("/share/wheel.bundle.json", "wb").write(clean[clean.find(b"{"):])
PY
  if curl -LsS -f -o /share/sigstore-trust-root.json \
      "$RELEASE_BASE/v$VERSION/sigstore-trust-root.json"; then
    echo "trust root descargado"
  else
    echo "SKIP: release sin asset sigstore-trust-root.json (anterior al trust root)"
    rm -f /share/sigstore-trust-root.json
    touch /share/.no-trust-root
  fi
' | tee "$ART/airgap-prep.log"

echo "-- A: verificación hermética online (sanity: flags --trust-config --offline)"
if podman exec "$NAME_A" bash -ec '
  test ! -f /share/.no-trust-root
  PT="$HOME/.local/share/uv/tools/archskillkit/bin/python"
  "$PT" -m sigstore --trust-config /share/sigstore-trust-root.json verify github \
    /share/wheel.whl --bundle /share/wheel.bundle.json \
    --repository Rubentxu/arch-skillkit --offline
'; then
  echo "verificación hermética: OK" | tee "$ART/attestation-hermetic.log"
else
  if podman exec "$NAME_A" test -f /share/.no-trust-root; then
    echo "SKIP hermética: release sin trust root asset" | tee "$ART/attestation-hermetic.log"
  else
    echo "FALLO verificación hermética" >&2
    exit 1
  fi
fi

echo "-- A: preparar caches para el contenedor offline"
podman exec "$NAME_A" bash -c 'cp /root/.local/bin/uv /share/uv'
podman rm -f "$NAME_A" >/dev/null

# ---------------------------------------------------------------------------
# Contenedor B — camino offline completo (sin red)
# ---------------------------------------------------------------------------
echo "-- B: contenedor SIN red — instalación offline desde cachés"
podman run -d --name "$NAME_B" --network=none \
  -v "$V_SHARE":/share:ro -v "$V_UVCACHE":/root/.cache/uv \
  -v "$V_ASKCACHE":/root/.cache/arch-skillkit \
  -v "$V_DATA":/root/.local/share \
  -v "$V_STATE":/root/.local/state \
  "$IMAGE" sleep infinity >/dev/null
podman exec "$NAME_B" bash -Eeuo pipefail -c '
  install -Dm755 /share/uv /usr/local/bin/uv
  export PATH="/usr/local/bin:/root/.local/bin:$PATH"
  WHEEL=$(ls /share/archskillkit-*.whl /share/wheel.whl 2>/dev/null | head -1 || echo "")
  if [ -n "$WHEEL" ]; then
    uv tool install --offline --python 3.12 --extra attestation "$WHEEL"
  else
    uv tool install --offline --python 3.12 --extra attestation archskillkit
  fi
  archskillkit setup --offline 2>&1
  archskillkit doctor > /tmp/doctor-offline.json || true
  cat /tmp/doctor-offline.json
  grep -q "\"status\": \"ready\"" /tmp/doctor-offline.json || exit 1
  echo "offline: instalación + runtime + doctor ready — OK"
  if [ ! -f /share/.no-trust-root ]; then
    PT="$HOME/.local/share/uv/tools/archskillkit/bin/python"
    "$PT" -m sigstore --trust-config /share/sigstore-trust-root.json verify github \
      /share/wheel.whl --bundle /share/wheel.bundle.json \
      --repository Rubentxu/arch-skillkit --offline
    echo "air-gap: verificación Sigstore hermética sin red — OK"
  else
    echo "air-gap: SKIP (release sin trust root asset)"
  fi
' | tee "$ART/offline.log"
podman cp "$NAME_B":/tmp/doctor-offline.json "$ART/doctor-offline.json"
podman rm -f "$NAME_B" >/dev/null

# ---------------------------------------------------------------------------
# Evidencia final
# ---------------------------------------------------------------------------
{
  echo "run_id=$RUN_ID"
  echo "version=$VERSION"
  echo "image=$IMAGE"
  echo "git=$(git -C "$ROOT" rev-parse HEAD)"
  echo "podman=$(podman --version)"
  echo "date=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$ART/versions.txt"

cat > "$ART/result.json" <<JSON
{"run_id": "$RUN_ID", "type": "verify-release", "version": "$VERSION",
 "result": "passed",
 "checks": ["install-online", "setup", "doctor-ready", "analysis-repo-clean",
            "corruption-detected", "offline-install-setup-doctor",
            "airgap-attestation-hermetic"]}
JSON

echo "== VERIFICACIÓN COMPLETA: passed — evidencia en $ART =="
