#!/usr/bin/env bats

setup() {
  bats_require_minimum_version 1.5.0
  ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd)"
  # shellcheck source=../../scripts/uat/lib.sh
  source "$ROOT/scripts/uat/lib.sh"
  SB="$(mktemp -d)"
  REPO="$SB/repo"
  EVIDENCE="$SB/evidence"
  mkdir -p "$REPO" "$EVIDENCE"
}

teardown() {
  chmod -R u+w "$SB" 2>/dev/null || true
  rm -rf "$SB"
}

@test "target configuration pins pipeline-kotlin to a full SHA" {
  run uat_resolve_target "$ROOT" pipeline-kotlin
  [ "$status" -eq 0 ]
  [ "$(jq -r .commit "$output")" = "3354f319095f70450d0fac85d970bbf3412e8635" ]
}

@test "unknown and unsafe target ids are rejected" {
  run uat_resolve_target "$ROOT" missing-target
  [ "$status" -ne 0 ]

  run uat_resolve_target "$ROOT" ../outside
  [ "$status" -ne 0 ]
}

@test "cleanup removes only an explicit child" {
  mkdir -p "$SB/runs/run-1/work"
  touch "$SB/runs/keep"

  run uat_safe_remove_dir "$SB/runs/run-1" "$SB/runs/run-1/work"
  [ "$status" -eq 0 ]
  [ ! -e "$SB/runs/run-1/work" ]
  [ -e "$SB/runs/keep" ]
}

@test "cleanup refuses its root and paths outside it" {
  mkdir -p "$SB/runs/run-1" "$SB/outside"

  run uat_safe_remove_dir "$SB/runs/run-1" "$SB/runs/run-1"
  [ "$status" -ne 0 ]
  [ -d "$SB/runs/run-1" ]

  run uat_safe_remove_dir "$SB/runs/run-1" "$SB/outside"
  [ "$status" -ne 0 ]
  [ -d "$SB/outside" ]
}

@test "git evidence detects a source-tree mutation" {
  git -C "$REPO" init -q
  git -C "$REPO" config user.name UAT
  git -C "$REPO" config user.email uat@example.invalid
  printf 'before\n' >"$REPO/file.txt"
  git -C "$REPO" add file.txt
  git -C "$REPO" commit -qm initial
  uat_git_evidence "$REPO" >"$EVIDENCE/before.json"

  printf 'after\n' >>"$REPO/file.txt"
  uat_git_evidence "$REPO" >"$EVIDENCE/after.json"

  run uat_same_git_evidence "$EVIDENCE/before.json" "$EVIDENCE/after.json"
  [ "$status" -ne 0 ]
}

@test "git evidence detects content changes in a pre-existing untracked file" {
  git -C "$REPO" init -q
  git -C "$REPO" config user.name UAT
  git -C "$REPO" config user.email uat@example.invalid
  printf 'tracked\n' >"$REPO/tracked.txt"
  git -C "$REPO" add tracked.txt
  git -C "$REPO" commit -qm initial
  printf 'same-size-A\n' >"$REPO/untracked.txt"
  uat_git_evidence "$REPO" >"$EVIDENCE/before.json"

  printf 'same-size-B\n' >"$REPO/untracked.txt"
  uat_git_evidence "$REPO" >"$EVIDENCE/after.json"

  run uat_same_git_evidence "$EVIDENCE/before.json" "$EVIDENCE/after.json"
  [ "$status" -ne 0 ]
}

@test "git evidence excludes ignored heavyweight content" {
  git -C "$REPO" init -q
  git -C "$REPO" config user.name UAT
  git -C "$REPO" config user.email uat@example.invalid
  printf 'ignored.bin\n' >"$REPO/.gitignore"
  git -C "$REPO" add .gitignore
  git -C "$REPO" commit -qm initial
  printf 'large-placeholder-A\n' >"$REPO/ignored.bin"
  uat_git_evidence "$REPO" >"$EVIDENCE/before.json"

  printf 'large-placeholder-B\n' >"$REPO/ignored.bin"
  uat_git_evidence "$REPO" >"$EVIDENCE/after.json"

  run uat_same_git_evidence "$EVIDENCE/before.json" "$EVIDENCE/after.json"
  [ "$status" -eq 0 ]
}

@test "a partial aggregate scan is not accepted" {
  run uat_scan_succeeded $'scan-outline: success\nscan-patterns: partial\nscan: partial\nrun_id: run-1'
  [ "$status" -ne 0 ]

  run uat_scan_succeeded $'scan: success\nrun_id: run-1'
  [ "$status" -eq 0 ]
}

@test "an explicit source override must be a non-bare worktree" {
  git init -q --bare "$SB/source.git"

  run uat_assert_worktree "$SB/source.git"
  [ "$status" -ne 0 ]
  [[ "$output" == *"bare"* ]]
}

@test "pure Just entry points forward documented UAT overrides" {
  run just --justfile "$ROOT/justfile" --working-directory "$ROOT" --dry-run uat
  [ "$status" -eq 0 ]
  [[ "$output" == *"UAT_SOURCE_REPO"* ]]
  [[ "$output" == *"UAT_STATE_ROOT"* ]]
  [[ "$output" == *"UAT_CACHE_ROOT"* ]]
  [[ "$output" == *"NODE_OPTIONS"* ]]
}

@test "runtime downloads are explicitly disabled during UAT" {
  unset MISE_AUTO_INSTALL
  run uat_disable_runtime_downloads
  [ "$status" -eq 0 ]
  [ "$output" = "0" ]
}

@test "resource limits default conservatively and allow positive overrides" {
  UAT_NO_MAIN=1 source "$ROOT/scripts/uat/uat.sh" >/dev/null
  unset ARCHSK_AST_GREP_THREADS ARCHSK_SEMGREP_JOBS ARCHSK_NODE_MAX_OLD_SPACE_SIZE_MB NODE_OPTIONS

  run capture_resource_limits
  [ "$status" -eq 0 ]
  [ "$(jq -r .ast_grep.threads <<<"$output")" = 1 ]
  [ "$(jq -r .semgrep.jobs <<<"$output")" = 1 ]
  [ "$(jq -r .node.max_old_space_size_mb <<<"$output")" = 512 ]

  ARCHSK_AST_GREP_THREADS=2 ARCHSK_SEMGREP_JOBS=3 \
    ARCHSK_NODE_MAX_OLD_SPACE_SIZE_MB=768 NODE_OPTIONS='--trace-warnings --max-old-space-size=2048' \
    run capture_resource_limits
  [ "$status" -eq 0 ]
  [ "$(jq -r .ast_grep.threads <<<"$output")" = 2 ]
  [ "$(jq -r .semgrep.jobs <<<"$output")" = 3 ]
  [ "$(jq -r .node.max_old_space_size_mb <<<"$output")" = 768 ]
  [ "$(jq -r .node.effective_node_options <<<"$output")" = '--trace-warnings --max-old-space-size=768' ]
}

@test "resource limit overrides reject zero, leading zeroes, and non-integers" {
  UAT_NO_MAIN=1 source "$ROOT/scripts/uat/uat.sh" >/dev/null
  ARCHSK_SEMGREP_JOBS=0 run capture_resource_limits
  [ "$status" -ne 0 ]
  [[ "$output" == *"ARCHSK_SEMGREP_JOBS must be a positive integer"* ]]

  ARCHSK_AST_GREP_THREADS=01 run capture_resource_limits
  [ "$status" -ne 0 ]
  [[ "$output" == *"ARCHSK_AST_GREP_THREADS must be a positive integer"* ]]

  ARCHSK_SEMGREP_JOBS=01 run capture_resource_limits
  [ "$status" -ne 0 ]
  [[ "$output" == *"ARCHSK_SEMGREP_JOBS must be a positive integer"* ]]

  ARCHSK_NODE_MAX_OLD_SPACE_SIZE_MB=0512 run capture_resource_limits
  [ "$status" -ne 0 ]
  [[ "$output" == *"ARCHSK_NODE_MAX_OLD_SPACE_SIZE_MB must be a positive integer"* ]]
}

@test "resource limit normalization preserves non-heap Node options" {
  UAT_NO_MAIN=1 source "$ROOT/scripts/uat/uat.sh" >/dev/null
  ARCHSK_NODE_MAX_OLD_SPACE_SIZE_MB=768 \
    NODE_OPTIONS='--trace-warnings --max-old-space-size=2048 --max_old_space_size 1024 --inspect=127.0.0.1:9229 --max_old_space_size=1536 --max-old-space-size 3072' \
    run capture_resource_limits
  [ "$status" -eq 0 ]
  [ "$(jq -r .node.effective_node_options <<<"$output")" = '--trace-warnings --inspect=127.0.0.1:9229 --max-old-space-size=768' ]
}

@test "finalization returns failure when repository evidence changed" {
  UAT_NO_MAIN=1 source "$ROOT/scripts/uat/uat.sh" >/dev/null
  RUN_ROOT="$SB/run"
  CHECKOUT="$RUN_ROOT/work/checkout"
  mkdir -p "$RUN_ROOT/evidence" "$RUN_ROOT/stages" "$CHECKOUT"
  git -C "$CHECKOUT" init -q
  git -C "$CHECKOUT" config user.name UAT
  git -C "$CHECKOUT" config user.email uat@example.invalid
  printf 'before\n' >"$CHECKOUT/file.txt"
  git -C "$CHECKOUT" add file.txt
  git -C "$CHECKOUT" commit -qm initial
  CHECKOUT_BEFORE="$RUN_ROOT/evidence/checkout-before.json"
  TARGET_ID=fixture
  TARGET_SHA="$(git -C "$CHECKOUT" rev-parse HEAD)"
  uat_git_evidence "$CHECKOUT" >"$CHECKOUT_BEFORE"
  printf 'mutation\n' >>"$CHECKOUT/file.txt"

  run finalize_run 0
  [ "$status" -ne 0 ]
  [ "$(jq -r .status "$RUN_ROOT/result.json")" = failed ]
}

@test "a result-write failure propagates and does not print a result path" {
  UAT_NO_MAIN=1 source "$ROOT/scripts/uat/uat.sh" >/dev/null
  RUN_ROOT="$SB/run"
  CHECKOUT=""
  mkdir -p "$RUN_ROOT"
  write_result() { return 1; }

  run finalize_run 0
  [ "$status" -ne 0 ]
  [[ "$output" != *"UAT result:"* ]]
}

make_source_fixture() {
  local source="$1"
  mkdir -p "$source"
  git -C "$source" init -q
  git -C "$source" config user.name UAT
  git -C "$source" config user.email uat@example.invalid
  printf 'source\n' >"$source/file.txt"
  git -C "$source" add file.txt
  git -C "$source" commit -qm initial
}

make_checkout_config() {
  local source="$1" normalized_remote="$2" config="$EVIDENCE/target.json"
  jq -n \
    --arg commit "$(git -C "$source" rev-parse HEAD)" \
    --arg normalized_remote "$normalized_remote" \
    '{id: "fixture", commit: $commit,
      repository: "https://example.invalid/fixture.git",
      normalized_remote: $normalized_remote,
      local_candidates: []}' >"$config"
  printf '%s\n' "$config"
}

@test "prepare_checkout aborts when the checked-out HEAD assertion fails" {
  UAT_NO_MAIN=1 source "$ROOT/scripts/uat/uat.sh" >/dev/null
  make_source_fixture "$REPO"
  config="$(make_checkout_config "$REPO" example.invalid/fixture)"
  RUN_ROOT="$SB/run"
  mkdir -p "$RUN_ROOT/evidence" "$RUN_ROOT/work"
  UAT_SOURCE_REPO="$REPO"
  TARGET_SHA="$(git -C "$REPO" rev-parse HEAD)"
  TARGET_ID=fixture
  TARGET_REPOSITORY="https://example.invalid/fixture.git"
  git() {
    if [ "$1" = -C ] && [[ "$2" == */work/checkout ]] &&
      [ "$3" = rev-parse ] && [ "$4" = HEAD ]; then
      printf '%040d\n' 0
      return 0
    fi
    command git "$@"
  }

  run prepare_checkout "$config"
  [ "$status" -ne 0 ]
  [[ "$output" == *"pinned SHA"* ]]
}

@test "prepare_checkout aborts when the normalized origin assertion fails" {
  UAT_NO_MAIN=1 source "$ROOT/scripts/uat/uat.sh" >/dev/null
  make_source_fixture "$REPO"
  config="$(make_checkout_config "$REPO" wrong.example/fixture)"
  RUN_ROOT="$SB/run"
  mkdir -p "$RUN_ROOT/evidence" "$RUN_ROOT/work"
  UAT_SOURCE_REPO="$REPO"
  TARGET_SHA="$(git -C "$REPO" rev-parse HEAD)"
  TARGET_ID=fixture
  TARGET_REPOSITORY="https://example.invalid/fixture.git"

  run prepare_checkout "$config"
  [ "$status" -ne 0 ]
  [[ "$output" == *"remote does not match"* ]]
}

@test "prepare_checkout aborts when the ephemeral checkout is dirty" {
  UAT_NO_MAIN=1 source "$ROOT/scripts/uat/uat.sh" >/dev/null
  make_source_fixture "$REPO"
  config="$(make_checkout_config "$REPO" example.invalid/fixture)"
  RUN_ROOT="$SB/run"
  mkdir -p "$RUN_ROOT/evidence" "$RUN_ROOT/work"
  UAT_SOURCE_REPO="$REPO"
  TARGET_SHA="$(git -C "$REPO" rev-parse HEAD)"
  TARGET_ID=fixture
  TARGET_REPOSITORY="https://example.invalid/fixture.git"
  git() {
    command git "$@"
    rc=$?
    if [ "$rc" -eq 0 ] && [ "$1" = -C ] && [[ "$2" == */work/checkout ]] &&
      [ "$3" = remote ] && [ "$4" = set-url ]; then
      printf 'dirty\n' >"$2/untracked.txt"
    fi
    return "$rc"
  }

  run prepare_checkout "$config"
  [ "$status" -ne 0 ]
  [[ "$output" == *"not clean"* ]]
}

@test "stage_report propagates report.sh failure even with a stale report" {
  UAT_NO_MAIN=1 source "$ROOT/scripts/uat/uat.sh" >/dev/null
  DISCOVERY_SCRIPTS="$SB/fake-scripts"
  WORKSPACE="$SB/workspace"
  CHECKOUT="$REPO"
  RUN_ROOT="$SB/run"
  mkdir -p "$DISCOVERY_SCRIPTS" "$WORKSPACE/reports" "$RUN_ROOT/payloads"
  printf '# stale\n' >"$WORKSPACE/reports/index.md"
  printf '#!/usr/bin/env bash\nexit 7\n' >"$DISCOVERY_SCRIPTS/report.sh"
  chmod +x "$DISCOVERY_SCRIPTS/report.sh"

  run stage_report
  [ "$status" -eq 7 ]
}

@test "finalization persists failure when the incoming process status is nonzero" {
  UAT_NO_MAIN=1 source "$ROOT/scripts/uat/uat.sh" >/dev/null
  RUN_ROOT="$SB/run"
  CHECKOUT=""
  TARGET_ID=fixture
  TARGET_SHA=deadbeef
  FINAL_STATUS=passed
  FINAL_REASON="stale success"
  mkdir -p "$RUN_ROOT/stages"

  run finalize_run 7
  [ "$status" -ne 0 ]
  [ "$(jq -r .status "$RUN_ROOT/result.json")" = failed ]
  [ "$(jq -r .reason "$RUN_ROOT/result.json")" = "runner exited with status 7" ]
}

@test "run_stage propagates failure to serialize its stage record" {
  UAT_NO_MAIN=1 source "$ROOT/scripts/uat/uat.sh" >/dev/null
  RUN_ROOT="$SB/run"
  mkdir -p "$RUN_ROOT/logs"
  stage_ok() { return 0; }

  run run_stage fixture stage_ok
  [ "$status" -ne 0 ]
}

@test "stage_scan rejects nonzero scanner exit despite a success marker" {
  UAT_NO_MAIN=1 source "$ROOT/scripts/uat/uat.sh" >/dev/null
  DISCOVERY_SCRIPTS="$SB/fake-scripts"
  RUN_ROOT="$SB/run"
  CHECKOUT="$REPO"
  WORKSPACE="$SB/workspace"
  mkdir -p "$DISCOVERY_SCRIPTS" "$RUN_ROOT/payloads" \
    "$WORKSPACE/evidence/raw"
  : >"$WORKSPACE/evidence/raw/ast-grep.jsonl"
  printf '{}\n' >"$WORKSPACE/evidence/raw/semgrep.json"
  printf '#!/usr/bin/env bash\nprintf '\''{"workspace":"%s"}\\n'\'' "$WORKSPACE"\n' \
    >"$DISCOVERY_SCRIPTS/workspace.sh"
  printf '#!/usr/bin/env bash\nprintf '\''scan: success\\nrun_id: run-1\\n'\''\nexit 9\n' \
    >"$DISCOVERY_SCRIPTS/scan.sh"
  chmod +x "$DISCOVERY_SCRIPTS/workspace.sh" "$DISCOVERY_SCRIPTS/scan.sh"

  run stage_scan
  [ "$status" -eq 9 ]
}

@test "Just preserves actual override values through a pure Devbox call" {
  mkdir -p "$SB/bin"
  printf '%s\n' \
    '#!/usr/bin/env bash' \
    'while [ "$#" -gt 0 ]; do' \
    '  case "$1" in' \
    '    --env) export "$2"; shift 2 ;;' \
    '    --) break ;;' \
    '    *) shift ;;' \
    '  esac' \
    'done' \
    'printf "source=<%s>\\nstate=<%s>\\ncache=<%s>\\n" "$UAT_SOURCE_REPO" "$UAT_STATE_ROOT" "$UAT_CACHE_ROOT"' \
    >"$SB/bin/devbox"
  chmod +x "$SB/bin/devbox"

  run env PATH="$SB/bin:$PATH" \
    UAT_SOURCE_REPO="$SB/source with spaces" \
    UAT_STATE_ROOT="$SB/state root" \
    UAT_CACHE_ROOT="$SB/cache root" \
    just --justfile "$ROOT/justfile" --working-directory "$ROOT" uat
  [ "$status" -eq 0 ]
  [[ "$output" == *"source=<$SB/source with spaces>"* ]]
  [[ "$output" == *"state=<$SB/state root>"* ]]
  [[ "$output" == *"cache=<$SB/cache root>"* ]]
}

@test "runtime_tool removes run XDG values and disables installation" {
  UAT_NO_MAIN=1 source "$ROOT/scripts/uat/uat.sh" >/dev/null
  mkdir -p "$SB/bin"
  printf '%s\n' \
    '#!/usr/bin/env bash' \
    'printf "data=%s cache=%s config=%s auto=%s mise_config=%s\\n" "${XDG_DATA_HOME-unset}" "${XDG_CACHE_HOME-unset}" "${XDG_CONFIG_HOME-unset}" "$MISE_AUTO_INSTALL" "$MISE_CONFIG_DIR"' \
    >"$SB/bin/mise"
  chmod +x "$SB/bin/mise"
  PATH="$SB/bin:$PATH"
  UAT_CACHE_BASE="$SB/shared-cache"
  XDG_DATA_HOME="$SB/run/data"
  XDG_CACHE_HOME="$SB/run/cache"
  XDG_CONFIG_HOME="$SB/run/config"

  run runtime_tool probe
  [ "$status" -eq 0 ]
  [[ "$output" == *"data=unset cache=unset config=unset auto=0"* ]]
  [[ "$output" == *"mise_config=$SB/shared-cache/tooling/mise-config"* ]]
}

@test "finalization detects mutation of the backing source tree" {
  UAT_NO_MAIN=1 source "$ROOT/scripts/uat/uat.sh" >/dev/null
  make_source_fixture "$REPO"
  RUN_ROOT="$SB/run"
  CHECKOUT=""
  SOURCE_REPO="$REPO"
  SOURCE_BEFORE="$RUN_ROOT/evidence/source-before.json"
  TARGET_ID=fixture
  TARGET_SHA="$(git -C "$REPO" rev-parse HEAD)"
  FINAL_STATUS=passed
  FINAL_REASON="all stages passed"
  mkdir -p "$RUN_ROOT/evidence" "$RUN_ROOT/stages"
  uat_git_evidence "$REPO" >"$SOURCE_BEFORE"
  printf 'mutation\n' >>"$REPO/file.txt"

  run finalize_run 0
  [ "$status" -ne 0 ]
  [ "$(jq -r .backing_source_unchanged "$RUN_ROOT/result.json")" = false ]
  [ "$(jq -r .status "$RUN_ROOT/result.json")" = failed ]
}

@test "finalization propagates cleanup failure without unsafe deletion" {
  UAT_NO_MAIN=1 source "$ROOT/scripts/uat/uat.sh" >/dev/null
  RUN_ROOT="$SB/run"
  CHECKOUT="$RUN_ROOT/work/checkout"
  TARGET_ID=fixture
  TARGET_SHA=deadbeef
  FINAL_STATUS=passed
  FINAL_REASON="all stages passed"
  mkdir -p "$RUN_ROOT/stages" "$CHECKOUT"
  uat_safe_remove_dir() { return 1; }

  run finalize_run 0
  [ "$status" -ne 0 ]
  [ "$(jq -r .status "$RUN_ROOT/result.json")" = failed ]
  [[ "$(jq -r .reason "$RUN_ROOT/result.json")" == *"cleanup failed"* ]]
}

@test "stage_scan rejects a success marker with zero scanner evidence" {
  UAT_NO_MAIN=1 source "$ROOT/scripts/uat/uat.sh" >/dev/null
  DISCOVERY_SCRIPTS="$SB/fake-scripts"
  RUN_ROOT="$SB/run"
  CHECKOUT="$REPO"
  WORKSPACE="$SB/workspace"
  mkdir -p "$DISCOVERY_SCRIPTS" "$RUN_ROOT/payloads" \
    "$WORKSPACE/evidence/raw"
  : >"$WORKSPACE/evidence/raw/ast-grep.jsonl"
  printf '{"results":[]}\n' >"$WORKSPACE/evidence/raw/semgrep.json"
  printf '#!/usr/bin/env bash\nprintf '\''{"workspace":"%s"}\\n'\'' "$WORKSPACE"\n' \
    >"$DISCOVERY_SCRIPTS/workspace.sh"
  printf '#!/usr/bin/env bash\nprintf '\''scan: success\\nrun_id: run-empty\\n'\''\n' \
    >"$DISCOVERY_SCRIPTS/scan.sh"
  chmod +x "$DISCOVERY_SCRIPTS/workspace.sh" "$DISCOVERY_SCRIPTS/scan.sh"

  run --separate-stderr stage_scan
  [ "$status" -ne 0 ]
  [ ! -f "$RUN_ROOT/payloads/scan.json" ]
}

@test "stage_ingest rejects an empty code index" {
  UAT_NO_MAIN=1 source "$ROOT/scripts/uat/uat.sh" >/dev/null
  TOOL_ENV="$SB/tool-env"
  RUN_ROOT="$SB/run"
  WORKSPACE="$SB/workspace"
  CHECKOUT="$REPO"
  mkdir -p "$TOOL_ENV/bin" "$RUN_ROOT/payloads" "$WORKSPACE/evidence/raw"
  printf 'run-empty\n' >"$RUN_ROOT/payloads/scan-run-id.txt"
  : >"$WORKSPACE/evidence/raw/ast-grep.jsonl"
  printf '{"results":[]}\n' >"$WORKSPACE/evidence/raw/semgrep.json"
  printf '%s\n' \
    '#!/usr/bin/env bash' \
    'case " $* " in' \
    '  *" init "*) jq -n '\''{project_id:"fixture"}'\'' ;;' \
    '  *" ingest-code "*) jq -n '\''{files:0,symbols:0,edges:0,warnings:[]}'\'' ;;' \
    '  *" index-stats "*) jq -n '\''{files:0,symbols:0,edges:0,kinds:{},edge_kinds:{}}'\'' ;;' \
    'esac' >"$TOOL_ENV/bin/python"
  chmod +x "$TOOL_ENV/bin/python"

  run --separate-stderr stage_ingest
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"code index is empty"* ]]
}

@test "failed backing-source evidence capture is persisted as unknown" {
  UAT_NO_MAIN=1 source "$ROOT/scripts/uat/uat.sh" >/dev/null
  make_source_fixture "$REPO"
  RUN_ROOT="$SB/run"
  CHECKOUT=""
  SOURCE_REPO="$REPO"
  SOURCE_BEFORE="$RUN_ROOT/evidence/source-before.json"
  TARGET_ID=fixture
  TARGET_SHA="$(git -C "$REPO" rev-parse HEAD)"
  FINAL_STATUS=passed
  FINAL_REASON="all stages passed"
  mkdir -p "$RUN_ROOT/evidence" "$RUN_ROOT/stages"
  uat_git_evidence "$REPO" >"$SOURCE_BEFORE"
  uat_git_evidence() { return 9; }

  run finalize_run 0
  [ "$status" -ne 0 ]
  [ "$(jq -r .status "$RUN_ROOT/result.json")" = failed ]
  [ "$(jq -r .backing_source_unchanged "$RUN_ROOT/result.json")" = null ]
  [ "$(jq -r .evidence_capture.backing_source "$RUN_ROOT/result.json")" = failed ]
}

@test "manifest states the Devbox realization boundary without a false network guarantee" {
  UAT_NO_MAIN=1 source "$ROOT/scripts/uat/uat.sh" >/dev/null
  RUN_ROOT="$SB/run"
  TARGET_ID=fixture
  TARGET_SHA=deadbeef
  TARGET_REPOSITORY="https://example.invalid/fixture.git"
  SOURCE_KIND=local
  SOURCE_REPO="$REPO"
  CHECKOUT="$RUN_ROOT/work/checkout"
  mkdir -p "$RUN_ROOT/evidence"
  capture_resource_limits >"$RUN_ROOT/evidence/resource-limits.json"

  run write_manifest
  [ "$status" -eq 0 ]
  jq -e 'has("network_fetch_during_run") | not' "$RUN_ROOT/manifest.json"
  [ "$(jq -r .reproducibility.pipeline.mise_auto_install "$RUN_ROOT/manifest.json")" = false ]
  [ "$(jq -r .reproducibility.pipeline.resource_limits.ast_grep.threads "$RUN_ROOT/manifest.json")" = 1 ]
  [ "$(jq -r .reproducibility.devbox.package_realization "$RUN_ROOT/manifest.json")" = "may-download-locked-packages-before-runner-starts" ]
  [ "$(jq -r '.reproducibility.devbox.inputs_locked == .reproducibility.devbox.lock_present' "$RUN_ROOT/manifest.json")" = true ]
}
