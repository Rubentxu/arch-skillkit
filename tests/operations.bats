#!/usr/bin/env bats
# Public seam: the root mise tasks used by contributors and CI.

load 'test_helper'

setup() {
  new_sandbox
}

@test "mise doctor distinguishes required and optional dependencies" {
  run mise run doctor

  [ "$status" -eq 0 ]
  [[ "$output" == *"Required dependencies"* ]]
  [[ "$output" == *"Optional dependencies"* ]]
  [[ "$output" == *"Python environment"* ]]
}

@test "mise test:bats runs BATS with the locked project interpreter" {
  local probe="$BATS_TEST_TMPDIR/interpreter-contract.bats"
  cat >"$probe" <<'EOF'
#!/usr/bin/env bats
@test "locked interpreter is exported" {
  [ "$ARCHSKILLKIT_PYTHON" = "$MISE_PROJECT_ROOT/python/.venv/bin/python" ]
  [ -x "$ARCHSKILLKIT_PYTHON" ]
}
EOF

  run env ARCHSKILLKIT_BATS_TARGET="$probe" mise run test:bats

  [ "$status" -eq 0 ]
  [[ "$output" == *"ok 1 locked interpreter is exported"* ]]
}

@test "Semgrep scan keeps settings and logs in XDG instead of HOME" {
  make_fixture_repo "$SB/repo" kotlin-spring

  run run_patterns "$SB/repo"

  [ "$status" -eq 0 ]
  [ -f "$SB/cache/arch-skillkit/semgrep/settings.yml" ]
  [ -f "$SB/cache/arch-skillkit/semgrep/semgrep.log" ]
}
