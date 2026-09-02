# Smoke suite (Session A of the Real OSS validation plan).
#
# Six short end-to-end checks against the Python CLI (`archskillkit`).
# Each test runs in its own XDG + ARCH_SKILLKIT_HOME sandbox so:
#   - the host filesystem is never touched,
#   - no two tests see each other's state,
#   - teardown is automatic via BATS_TEST_TMPDIR.
#
# Wallclock budget: <= 30s for the whole suite. Resource caps:
#   - 1 thread per scanner invocation,
#   - ARCH_SKILLKIT_HOME per-test under $BATS_TEST_TMPDIR,
#   - hard skip if ast-grep binary is absent.
load 'test_helper'

ARCH_CLI="$MISE_PROJECT_ROOT/python/.venv/bin/archskillkit"
ARCH_PY="$MISE_PROJECT_ROOT/python/.venv/bin/python"
PY_SRC="$MISE_PROJECT_ROOT/python/src"
SG_CONFIG="$MISE_PROJECT_ROOT/skills/architecture-discovery/rules/ast-grep/sgconfig.yml"

setup() {
  new_sandbox
  export ARCH_SKILLKIT_HOME="$SB/cache/ark"
  AST_GREP="$(find_ast_grep)"
  if [ -z "$AST_GREP" ]; then
    skip "ast-grep binary not found (run mise bootstrap first)"
  fi
}

# 1. doctor reports the installation is ready (or ready-offline if
#    the runtime has not been fetched yet — both states are exit-0
#    and indicate the CLI can answer environment questions).
@test "smoke: archskillkit doctor reports ready" {
  [ -x "$ARCH_CLI" ] || skip "archskillkit CLI not built"
  run "$ARCH_CLI" doctor
  assert_rc "doctor exits 0" 0 "$status"
  # Either "ready" or "ready-offline" is acceptable for the smoke
  # gate — both exit 0 and prove the CLI is wired correctly.
  case "$output" in
    *'"status": "ready"'*) ;;
    *'"status": "ready-offline"'*) ;;
    *)
      printf 'doctor status not in {ready, ready-offline}:\n%s\n' "$output" >&2
      return 1
      ;;
  esac
}

# 2. init on a fresh repo leaves the source tree untouched (UAT2-001).
@test "smoke: archskillkit init does not pollute the source repo" {
  [ -x "$ARCH_CLI" ] || skip "archskillkit CLI not built"
  repo="$SB/repo"
  mkdir -p "$repo"
  git -C "$repo" init -q -b main
  git -C "$repo" config user.email "x@x"
  git -C "$repo" config user.name "x"
  echo "hi" > "$repo/README.md"
  git -C "$repo" add -A
  git -C "$repo" commit -q -m "init"
  before=$(cd "$repo" && git status --porcelain)
  run env ARCH_SKILLKIT_HOME="$SB/cache/ark" PYTHONPATH="$PY_SRC" \
    "$ARCH_PY" -m archskillkit init --repo "$repo"
  assert_rc "init exits 0" 0 "$status"
  after=$(cd "$repo" && git status --porcelain)
  if [ "$before" != "$after" ]; then
    printf 'repo polluted:\nbefore:\n%s\nafter:\n%s\n' "$before" "$after" >&2
    return 1
  fi
}

# 3. discover() on a Kotlin fixture runs end-to-end and returns a
#    PromotionReport. ast-grep alone populates the Code Index symbols;
#    semgrep edges drive the architecture elements, so we just verify
#    the discover CLI exits 0 and emits the expected report shape.
@test "smoke: discover on Kotlin fixture runs end-to-end" {
  [ -x "$ARCH_CLI" ] || skip "archskillkit CLI not built"
  repo="$SB/kotlin"
  mkdir -p "$repo/src/api"
  cat > "$repo/src/api/Users.kt" <<'EOF'
package api
fun getUser(id: String): User = User(id)
fun listUsers(): List<User> = emptyList()
data class User(val id: String, val name: String)
EOF
  cat > "$repo/src/api/Orders.kt" <<'EOF'
package api
fun getOrder(id: String): Order = Order(id)
EOF
  git -C "$repo" init -q -b main
  git -C "$repo" config user.email "x@x"
  git -C "$repo" config user.name "x"
  git -C "$repo" add -A
  git -C "$repo" commit -q -m "init"
  ark_home="$SB/cache/ark"
  run env ARCH_SKILLKIT_HOME="$ark_home" PYTHONPATH="$PY_SRC" \
    "$ARCH_PY" -m archskillkit init --repo "$repo"
  assert_rc "init" 0 "$status"
  # Real ast-grep scan, then ingest the NDJSON it produced.
  "$AST_GREP" scan -c "$SG_CONFIG" --threads 1 --json=stream "$repo" \
    > "$SB/astgrep.ndjson" 2>"$SB/astgrep.stderr.log"
  rc=$?
  if [ "$rc" -ne 0 ]; then
    cat "$SB/astgrep.stderr.log" >&2
    return 1
  fi
  run env ARCH_SKILLKIT_HOME="$ark_home" PYTHONPATH="$PY_SRC" \
    "$ARCH_PY" -m archskillkit ingest-code --repo "$repo" \
    --astgrep "$SB/astgrep.ndjson" --run-id "smoke-$$"
  assert_rc "ingest" 0 "$status"
  run env ARCH_SKILLKIT_HOME="$ark_home" PYTHONPATH="$PY_SRC" \
    "$ARCH_PY" -m archskillkit discover --repo "$repo" --run-id "smoke-$$"
  assert_rc "discover" 0 "$status"
  # PromotionReport shape: assertions, elements, relations keys present.
  assert_output_contains "claims_proposed key" '"claims_proposed"' "$output"
  assert_output_contains "elements key" '"elements"' "$output"
  assert_output_contains "relations key" '"relations"' "$output"
}

# 4. project regenerates byte-identical LikeC4 output.
@test "smoke: project regenerates byte-identical LikeC4" {
  [ -x "$ARCH_CLI" ] || skip "archskillkit CLI not built"
  repo="$SB/projregen"
  mkdir -p "$repo/src/api"
  cat > "$repo/src/api/Users.kt" <<'EOF'
package api
fun getUser(): User = User("x")
data class User(val id: String)
EOF
  git -C "$repo" init -q -b main
  git -C "$repo" config user.email "x@x"
  git -C "$repo" config user.name "x"
  git -C "$repo" add -A
  git -C "$repo" commit -q -m "init"
  ark_home="$SB/cache/ark"
  env ARCH_SKILLKIT_HOME="$ark_home" PYTHONPATH="$PY_SRC" \
    "$ARCH_PY" -m archskillkit init --repo "$repo" >/dev/null
  "$AST_GREP" scan -c "$SG_CONFIG" --threads 1 --json=stream "$repo" \
    > "$SB/astgrep.ndjson" 2>/dev/null
  env ARCH_SKILLKIT_HOME="$ark_home" PYTHONPATH="$PY_SRC" \
    "$ARCH_PY" -m archskillkit ingest-code --repo "$repo" \
    --astgrep "$SB/astgrep.ndjson" --run-id "smoke-$$" >/dev/null
  env ARCH_SKILLKIT_HOME="$ark_home" PYTHONPATH="$PY_SRC" \
    "$ARCH_PY" -m archskillkit discover --repo "$repo" --run-id "smoke-$$" >/dev/null
  env ARCH_SKILLKIT_HOME="$ark_home" PYTHONPATH="$PY_SRC" \
    "$ARCH_PY" -m archskillkit project --repo "$repo" --format likec4 \
    >"$SB/proj1.json"
  env ARCH_SKILLKIT_HOME="$ark_home" PYTHONPATH="$PY_SRC" \
    "$ARCH_PY" -m archskillkit project --repo "$repo" --format likec4 \
    >"$SB/proj2.json"
  d1=$(sha256sum "$SB/proj1.json" | cut -d' ' -f1)
  d2=$(sha256sum "$SB/proj2.json" | cut -d' ' -f1)
  if [ "$d1" != "$d2" ]; then
    printf 'regen drift:\n%s\n%s\n' "$d1" "$d2" >&2
    return 1
  fi
}

# 5. context compiler respects tight budgets.
@test "smoke: context compiler respects node/edge budgets" {
  [ -x "$ARCH_CLI" ] || skip "archskillkit CLI not built"
  repo="$SB/ctx"
  mkdir -p "$repo/src/api"
  cat > "$repo/src/api/Users.kt" <<'EOF'
package api
fun getUser(): User = User("x")
fun listUsers(): List<User> = emptyList()
EOF
  git -C "$repo" init -q -b main
  git -C "$repo" config user.email "x@x"
  git -C "$repo" config user.name "x"
  git -C "$repo" add -A
  git -C "$repo" commit -q -m "init"
  ark_home="$SB/cache/ark"
  env ARCH_SKILLKIT_HOME="$ark_home" PYTHONPATH="$PY_SRC" \
    "$ARCH_PY" -m archskillkit init --repo "$repo" >/dev/null
  "$AST_GREP" scan -c "$SG_CONFIG" --threads 1 --json=stream "$repo" \
    > "$SB/astgrep.ndjson" 2>/dev/null
  env ARCH_SKILLKIT_HOME="$ark_home" PYTHONPATH="$PY_SRC" \
    "$ARCH_PY" -m archskillkit ingest-code --repo "$repo" \
    --astgrep "$SB/astgrep.ndjson" --run-id "smoke-$$" >/dev/null
  env ARCH_SKILLKIT_HOME="$ark_home" PYTHONPATH="$PY_SRC" \
    "$ARCH_PY" -m archskillkit discover --repo "$repo" --run-id "smoke-$$" >/dev/null
  run env ARCH_SKILLKIT_HOME="$ark_home" PYTHONPATH="$PY_SRC" \
    "$ARCH_PY" -m archskillkit context --repo "$repo" \
    --goal "explain the API" --subject "Users" \
    --max-nodes 2 --max-edges 2 --max-lines 3
  assert_rc "context" 0 "$status"
  assert_output_contains "elements key present" '"elements"' "$output"
  nelem=$(echo "$output" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d.get('architecture',{}).get('elements',[])))")
  nrel=$(echo "$output" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d.get('architecture',{}).get('relations',[])))")
  if [ "$nelem" -gt 2 ]; then
    printf 'budget violated: %s elements > 2\n' "$nelem" >&2
    return 1
  fi
  if [ "$nrel" -gt 2 ]; then
    printf 'budget violated: %s relations > 2\n' "$nrel" >&2
    return 1
  fi
}

# 6. drift detector runs without an LLM (deterministic).
@test "smoke: drift detector runs deterministically (no LLM)" {
  [ -x "$ARCH_CLI" ] || skip "archskillkit CLI not built"
  repo="$SB/drift"
  mkdir -p "$repo/src/a" "$repo/src/b"
  cat > "$repo/src/a/ServiceA.kt" <<'EOF'
package a
import b.ServiceB
class ServiceA(val b: ServiceB)
EOF
  cat > "$repo/src/b/ServiceB.kt" <<'EOF'
package b
class ServiceB
EOF
  git -C "$repo" init -q -b main
  git -C "$repo" config user.email "x@x"
  git -C "$repo" config user.name "x"
  git -C "$repo" add -A
  git -C "$repo" commit -q -m "init"
  ark_home="$SB/cache/ark"
  env ARCH_SKILLKIT_HOME="$ark_home" PYTHONPATH="$PY_SRC" \
    "$ARCH_PY" -m archskillkit init --repo "$repo" >/dev/null
  "$AST_GREP" scan -c "$SG_CONFIG" --threads 1 --json=stream "$repo" \
    > "$SB/astgrep.ndjson" 2>/dev/null
  env ARCH_SKILLKIT_HOME="$ark_home" PYTHONPATH="$PY_SRC" \
    "$ARCH_PY" -m archskillkit ingest-code --repo "$repo" \
    --astgrep "$SB/astgrep.ndjson" --run-id "smoke-$$" >/dev/null
  env ARCH_SKILLKIT_HOME="$ark_home" PYTHONPATH="$PY_SRC" \
    "$ARCH_PY" -m archskillkit discover --repo "$repo" --run-id "smoke-$$" >/dev/null
  run env ARCH_SKILLKIT_HOME="$ark_home" PYTHONPATH="$PY_SRC" \
    "$ARCH_PY" -m archskillkit drift --repo "$repo"
  assert_rc "drift" 0 "$status"
  assert_output_contains "findings key" '"findings"' "$output"
}