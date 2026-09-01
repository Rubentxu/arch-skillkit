set shell := ["bash", "-euo", "pipefail", "-c"]

default:
    @just --list

# Execute the GitHub Actions-compatible recipe locally; this path is outside
# .github/ so it is never discovered or run by GitHub.
ci-github-local:
    act push --workflows ci/github-actions/ci.yml --no-cache-server

# Verify the pure UAT toolchain and preloaded scanner/runtime dependencies.
uat-doctor:
    devbox run --pure \
      --env "UAT_SOURCE_REPO=${UAT_SOURCE_REPO:-}" \
      --env "UAT_STATE_ROOT=${UAT_STATE_ROOT:-}" \
      --env "UAT_CACHE_ROOT=${UAT_CACHE_ROOT:-}" \
      --env "ARCHSK_AST_GREP_THREADS=${ARCHSK_AST_GREP_THREADS:-}" \
      --env "ARCHSK_SEMGREP_JOBS=${ARCHSK_SEMGREP_JOBS:-}" \
      --env "ARCHSK_NODE_MAX_OLD_SPACE_SIZE_MB=${ARCHSK_NODE_MAX_OLD_SPACE_SIZE_MB:-}" \
      --env "NODE_OPTIONS=${NODE_OPTIONS:-}" \
      -- bash scripts/uat/uat.sh doctor

# Explicitly download/install locked Python and scanner dependencies.
uat-bootstrap:
    devbox run --pure \
      --env "UAT_SOURCE_REPO=${UAT_SOURCE_REPO:-}" \
      --env "UAT_STATE_ROOT=${UAT_STATE_ROOT:-}" \
      --env "UAT_CACHE_ROOT=${UAT_CACHE_ROOT:-}" \
      --env "ARCHSK_AST_GREP_THREADS=${ARCHSK_AST_GREP_THREADS:-}" \
      --env "ARCHSK_SEMGREP_JOBS=${ARCHSK_SEMGREP_JOBS:-}" \
      --env "ARCHSK_NODE_MAX_OLD_SPACE_SIZE_MB=${ARCHSK_NODE_MAX_OLD_SPACE_SIZE_MB:-}" \
      --env "NODE_OPTIONS=${NODE_OPTIONS:-}" \
      -- bash scripts/uat/uat.sh bootstrap

# Explicit network operation: cache and SHA-verify a target repository.
uat-fetch target="pipeline-kotlin":
    devbox run --pure \
      --env "UAT_SOURCE_REPO=${UAT_SOURCE_REPO:-}" \
      --env "UAT_STATE_ROOT=${UAT_STATE_ROOT:-}" \
      --env "UAT_CACHE_ROOT=${UAT_CACHE_ROOT:-}" \
      --env "ARCHSK_AST_GREP_THREADS=${ARCHSK_AST_GREP_THREADS:-}" \
      --env "ARCHSK_SEMGREP_JOBS=${ARCHSK_SEMGREP_JOBS:-}" \
      --env "ARCHSK_NODE_MAX_OLD_SPACE_SIZE_MB=${ARCHSK_NODE_MAX_OLD_SPACE_SIZE_MB:-}" \
      --env "NODE_OPTIONS=${NODE_OPTIONS:-}" \
      -- bash scripts/uat/uat.sh fetch {{ quote(target) }}

# Run a cached/local target without performing network access.
uat target="pipeline-kotlin":
    devbox run --pure \
      --env "UAT_SOURCE_REPO=${UAT_SOURCE_REPO:-}" \
      --env "UAT_STATE_ROOT=${UAT_STATE_ROOT:-}" \
      --env "UAT_CACHE_ROOT=${UAT_CACHE_ROOT:-}" \
      --env "ARCHSK_AST_GREP_THREADS=${ARCHSK_AST_GREP_THREADS:-}" \
      --env "ARCHSK_SEMGREP_JOBS=${ARCHSK_SEMGREP_JOBS:-}" \
      --env "ARCHSK_NODE_MAX_OLD_SPACE_SIZE_MB=${ARCHSK_NODE_MAX_OLD_SPACE_SIZE_MB:-}" \
      --env "NODE_OPTIONS=${NODE_OPTIONS:-}" \
      -- bash scripts/uat/uat.sh run {{ quote(target) }}

# Focused shell tests for target resolution and cleanup safety.
uat-test:
    devbox run --pure \
      --env "UAT_SOURCE_REPO=${UAT_SOURCE_REPO:-}" \
      --env "UAT_STATE_ROOT=${UAT_STATE_ROOT:-}" \
      --env "UAT_CACHE_ROOT=${UAT_CACHE_ROOT:-}" \
      --env "ARCHSK_AST_GREP_THREADS=${ARCHSK_AST_GREP_THREADS:-}" \
      --env "ARCHSK_SEMGREP_JOBS=${ARCHSK_SEMGREP_JOBS:-}" \
      --env "ARCHSK_NODE_MAX_OLD_SPACE_SIZE_MB=${ARCHSK_NODE_MAX_OLD_SPACE_SIZE_MB:-}" \
      --env "NODE_OPTIONS=${NODE_OPTIONS:-}" \
      -- bats tests/uat

[group('verify')]
[doc('Verificación Fase 2 en contenedor limpio (online): instala el release, setup, doctor, análisis, corrupción')]
verify-release version="0.3.0":
    ./scripts/verify/run-verify.sh "{{version}}"

[group('verify')]
[doc('Verificación Fase 2 completa incluyendo camino OFFLINE (dos contenedores)')]
verify-release-full version="0.3.0":
    ./scripts/verify/run-verify.sh "{{version}}"

[group('dogfood')]
[doc('ArchSkillKit analizando ArchSkillKit con su propio runtime (drift + evidencia)')]
dogfood:
    ./scripts/dogfood.sh
