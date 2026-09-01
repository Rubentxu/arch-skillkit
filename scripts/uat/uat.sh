#!/usr/bin/env bash
# Local UAT tracer bullet for a real, pinned repository.
# Devbox/Just own the entry point; this script owns lifecycle and evidence.
set -uo pipefail

SCRIPT_DIR="$(cd "${BASH_SOURCE[0]%/*}" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
# shellcheck source=lib.sh
. "$SCRIPT_DIR/lib.sh"

DISCOVERY_DIR="$ROOT/skills/architecture-discovery"
DISCOVERY_SCRIPTS="$DISCOVERY_DIR/scripts"
RUNTIME_DIR="$DISCOVERY_DIR/runtime"
# shellcheck source=../../skills/architecture-discovery/scripts/lib/common.sh
. "$DISCOVERY_SCRIPTS/lib/common.sh"

UAT_STATE_BASE="${UAT_STATE_ROOT:-${XDG_STATE_HOME:-$HOME/.local/state}/arch-skillkit-uat}"
UAT_CACHE_BASE="${UAT_CACHE_ROOT:-${XDG_CACHE_HOME:-$HOME/.cache}/arch-skillkit-uat}"
TOOL_ENV="$UAT_CACHE_BASE/tooling/python-env"
UV_CACHE="$UAT_CACHE_BASE/tooling/uv"
SOURCE_CACHE="$UAT_CACHE_BASE/sources"

RUN_ROOT=""
CHECKOUT=""
SOURCE_REPO=""
SOURCE_KIND=""
SOURCE_BEFORE=""
CHECKOUT_BEFORE=""
WORKSPACE=""
TARGET_ID=""
TARGET_SHA=""
TARGET_REPOSITORY=""
FINAL_STATUS="error"
FINAL_REASON="runner exited before completion"
STAGE_COUNTER=0
FINALIZED=0
CHECKOUT_CAPTURE_STATUS="not-applicable"
SOURCE_CAPTURE_STATUS="not-applicable"

usage() {
  cat <<'EOF'
Usage: scripts/uat/uat.sh <command> [target]

Commands:
  doctor                verify the pure toolchain and cached runtime
  bootstrap             explicitly download locked runtime dependencies
  fetch [target]        explicitly cache a network repository and verify SHA
  run [target]          run UAT from a local/cached source, without network fetch

Default target: pipeline-kotlin
EOF
}

target_value() {
  local config="$1" field="$2"
  jq -er --arg field "$field" '.[$field]' "$config"
}

source_cache_path() {
  local target="$1"
  printf '%s/%s.git\n' "$SOURCE_CACHE" "$target"
}

find_local_source() {
  local config="$1" candidate path expected_sha
  expected_sha="$(target_value "$config" commit)"

  if [ -n "${UAT_SOURCE_REPO:-}" ]; then
    candidate="$(realpath "${UAT_SOURCE_REPO}")" || return 1
    uat_assert_worktree "$candidate" || return 1
    git -C "$candidate" cat-file -e "$expected_sha^{commit}" 2>/dev/null || {
      uat_die "UAT_SOURCE_REPO does not contain pinned commit $expected_sha"
      return 1
    }
    printf 'local\t%s\n' "$candidate"
    return 0
  fi

  while IFS= read -r candidate; do
    path="$HOME/$candidate"
    if uat_assert_worktree "$path" >/dev/null 2>&1 &&
      git -C "$path" cat-file -e "$expected_sha^{commit}" 2>/dev/null; then
      printf 'local\t%s\n' "$(realpath "$path")"
      return 0
    fi
  done < <(jq -r '.local_candidates[]' "$config")

  candidate="$(source_cache_path "$(target_value "$config" id)")"
  if git --git-dir="$candidate" cat-file -e "$expected_sha^{commit}" 2>/dev/null; then
    printf 'cache\t%s\n' "$(realpath "$candidate")"
    return 0
  fi
  return 1
}

runtime_tool() {
  local config_dir="$UAT_CACHE_BASE/tooling/mise-config"
  local semgrep_dir="$UAT_CACHE_BASE/tooling/semgrep" node_heap node_options
  mkdir -p "$config_dir" "$semgrep_dir"
  if [ ! -f "$semgrep_dir/version" ]; then
    printf '%s\n{}\n' "$(date +%s)" >"$semgrep_dir/version"
  fi
  node_heap="$(arch_node_max_old_space_size_mb)" || return
  node_options="$(arch_node_options_with_heap "$node_heap")" || return
  env -u XDG_DATA_HOME -u XDG_CACHE_HOME -u XDG_CONFIG_HOME \
    MISE_AUTO_INSTALL=0 \
    MISE_CONFIG_DIR="$config_dir" \
    SEMGREP_SETTINGS_FILE="$semgrep_dir/settings.yml" \
    SEMGREP_VERSION_CACHE_PATH="$semgrep_dir/version" \
    SEMGREP_LOG_FILE="$semgrep_dir/semgrep.log" \
    NODE_OPTIONS="$node_options" \
    mise exec -C "$RUNTIME_DIR" -- "$@"
}

capture_resource_limits() {
  local astgrep_threads semgrep_jobs node_heap node_options
  astgrep_threads="$(arch_ast_grep_threads)" || return
  semgrep_jobs="$(arch_semgrep_jobs)" || return
  node_heap="$(arch_node_max_old_space_size_mb)" || return
  node_options="$(arch_node_options_with_heap "$node_heap")" || return
  jq -n \
    --argjson astgrep_threads "$astgrep_threads" \
    --argjson semgrep_jobs "$semgrep_jobs" \
    --argjson node_max_old_space_size_mb "$node_heap" \
    --arg node_options "$node_options" \
    '{ast_grep: {threads: $astgrep_threads},
      semgrep: {jobs: $semgrep_jobs},
      node: {max_old_space_size_mb: $node_max_old_space_size_mb,
        effective_node_options: $node_options}}'
}

capture_versions() {
  local astgrep semgrep likec4
  astgrep="$(runtime_tool ast-grep --version 2>/dev/null || printf absent)"
  semgrep="$(runtime_tool semgrep --version 2>/dev/null || printf absent)"
  likec4="$(runtime_tool likec4 --version 2>/dev/null || printf absent)"
  jq -n \
    --arg bash "$BASH_VERSION" \
    --arg git "$(git --version)" \
    --arg jq "$(jq --version)" \
    --arg python "$($TOOL_ENV/bin/python --version 2>&1 || printf absent)" \
    --arg uv "$(uv --version 2>&1 || printf absent)" \
    --arg mise "$(mise --version 2>&1 | head -n 1 || printf absent)" \
    --arg astgrep "$astgrep" \
    --arg semgrep "$semgrep" \
    --arg likec4 "$likec4" \
    '{bash: $bash, git: $git, jq: $jq, python: $python, uv: $uv,
      mise: $mise, ast_grep: $astgrep, semgrep: $semgrep, likec4: $likec4}'
}

write_result() {
  local checkout_unchanged=null source_unchanged=null known_defect=false
  local stage_files=()
  [ -n "$RUN_ROOT" ] || return 0

  if [ "$CHECKOUT_CAPTURE_STATUS" = captured ]; then
    if [ -f "$RUN_ROOT/evidence/checkout-before.json" ] &&
      [ -f "$RUN_ROOT/evidence/checkout-after.json" ] &&
      uat_same_git_evidence "$RUN_ROOT/evidence/checkout-before.json" \
        "$RUN_ROOT/evidence/checkout-after.json"; then
      checkout_unchanged=true
    elif [ -f "$RUN_ROOT/evidence/checkout-before.json" ] &&
      [ -f "$RUN_ROOT/evidence/checkout-after.json" ]; then
      checkout_unchanged=false
    fi
  fi
  if [ "$SOURCE_CAPTURE_STATUS" = captured ]; then
    if [ -f "$RUN_ROOT/evidence/source-before.json" ] &&
      [ -f "$RUN_ROOT/evidence/source-after.json" ] &&
      uat_same_git_evidence "$RUN_ROOT/evidence/source-before.json" \
        "$RUN_ROOT/evidence/source-after.json"; then
      source_unchanged=true
    elif [ -f "$RUN_ROOT/evidence/source-before.json" ] &&
      [ -f "$RUN_ROOT/evidence/source-after.json" ]; then
      source_unchanged=false
    fi
  fi
  if [ -f "$RUN_ROOT/payloads/validation.json" ] &&
    jq -e '.project_metadata.valid == false' "$RUN_ROOT/payloads/validation.json" >/dev/null 2>&1; then
    known_defect=true
  fi

  if [ "$checkout_unchanged" = false ] || [ "$source_unchanged" = false ]; then
    if [ "$FINAL_STATUS" != failed ]; then
      FINAL_REASON="analyzed repository changed during UAT"
    fi
    FINAL_STATUS="failed"
  fi

  shopt -s nullglob
  stage_files=("$RUN_ROOT"/stages/*.json)
  shopt -u nullglob
  if [ "${#stage_files[@]}" -gt 0 ]; then
    jq -s '.' "${stage_files[@]}" >"$RUN_ROOT/.stages.json" || return 1
  else
    printf '[]\n' >"$RUN_ROOT/.stages.json" || return 1
  fi
  jq -n \
    --arg schema_version "1" \
    --arg run_id "$(basename "$RUN_ROOT")" \
    --arg target "$TARGET_ID" \
    --arg commit "$TARGET_SHA" \
    --arg status "$FINAL_STATUS" \
    --arg reason "$FINAL_REASON" \
    --arg artifact_root "$RUN_ROOT" \
    --arg workspace "$WORKSPACE" \
    --argjson checkout_unchanged "$checkout_unchanged" \
    --argjson source_unchanged "$source_unchanged" \
    --argjson known_metadata_defect "$known_defect" \
    --arg checkout_capture "$CHECKOUT_CAPTURE_STATUS" \
    --arg source_capture "$SOURCE_CAPTURE_STATUS" \
    --slurpfile stages "$RUN_ROOT/.stages.json" \
    '{schema_version: ($schema_version | tonumber), run_id: $run_id,
      target: $target, commit: $commit, status: $status, reason: $reason,
      artifact_root: $artifact_root, architecture_workspace: $workspace,
      repository_unchanged: $checkout_unchanged,
      backing_source_unchanged: $source_unchanged,
      evidence_capture: {checkout: $checkout_capture,
        backing_source: $source_capture},
      known_project_metadata_defect_observed: $known_metadata_defect,
      stages: $stages[0],
      visual_review: {
        status: "pending-human-review",
        note: "Automated syntax/build checks are not a human visual review."
      }}' >"$RUN_ROOT/result.json" || return 1
  rm -f "$RUN_ROOT/.stages.json" || return 1
}

finalize_run() {
  local original_rc="$1" final_rc="$1" result_written=0
  [ "$FINALIZED" -eq 0 ] || return 0
  FINALIZED=1
  set +e

  if [ "$original_rc" -ne 0 ]; then
    if [ "$FINAL_STATUS" != failed ]; then
      FINAL_REASON="runner exited with status $original_rc"
    fi
    FINAL_STATUS="failed"
  fi

  if [ -n "$CHECKOUT" ] && [ -d "$CHECKOUT/.git" ]; then
    CHECKOUT_CAPTURE_STATUS="failed"
    if uat_git_evidence "$CHECKOUT" >"$RUN_ROOT/evidence/checkout-after.json"; then
      CHECKOUT_CAPTURE_STATUS="captured"
    else
      FINAL_STATUS="failed"
      FINAL_REASON="checkout evidence capture failed"
      final_rc=1
    fi
  fi
  if [ -n "$SOURCE_BEFORE" ] && [ -n "$SOURCE_REPO" ] &&
    git -C "$SOURCE_REPO" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    SOURCE_CAPTURE_STATUS="failed"
    if uat_git_evidence "$SOURCE_REPO" >"$RUN_ROOT/evidence/source-after.json"; then
      SOURCE_CAPTURE_STATUS="captured"
    else
      FINAL_STATUS="failed"
      FINAL_REASON="backing source evidence capture failed"
      final_rc=1
    fi
  fi
  if [ -n "$CHECKOUT" ] && [ -n "$RUN_ROOT" ]; then
    uat_safe_remove_dir "$RUN_ROOT/work" "$CHECKOUT" || {
      FINAL_STATUS="failed"
      FINAL_REASON="ephemeral checkout cleanup failed"
      final_rc=1
    }
  fi
  if write_result; then
    result_written=1
  else
    printf 'error: failed to persist UAT result\n' >&2
    final_rc=1
  fi
  if [ "$FINAL_STATUS" != passed ]; then
    final_rc=1
  fi
  if [ "$result_written" -eq 1 ]; then
    printf 'UAT result: %s\n' "$RUN_ROOT/result.json" >&2
  fi
  return "$final_rc"
}

on_run_exit() {
  local original_rc=$? final_rc
  trap - EXIT HUP INT TERM
  finalize_run "$original_rc"
  final_rc=$?
  exit "$final_rc"
}

run_stage() {
  local name="$1" function_name="$2" started finished rc record_rc stage_id stdout_log stderr_log
  shift 2
  STAGE_COUNTER=$((STAGE_COUNTER + 1))
  stage_id="$(printf '%02d-%s' "$STAGE_COUNTER" "$name")"
  stdout_log="$RUN_ROOT/logs/$stage_id.stdout.log"
  stderr_log="$RUN_ROOT/logs/$stage_id.stderr.log"
  started="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  "$function_name" "$@" >"$stdout_log" 2>"$stderr_log"
  rc=$?
  finished="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  jq -n \
    --arg name "$name" --arg started_at "$started" --arg finished_at "$finished" \
    --arg stdout_log "$stdout_log" --arg stderr_log "$stderr_log" \
    --argjson exit_code "$rc" \
    '{name: $name, status: (if $exit_code == 0 then "passed" else "failed" end),
      exit_code: $exit_code, started_at: $started_at, finished_at: $finished_at,
      stdout_log: $stdout_log, stderr_log: $stderr_log}' \
    >"$RUN_ROOT/stages/$stage_id.json"
  record_rc=$?
  [ "$record_rc" -eq 0 ] || return "$record_rc"
  return "$rc"
}

stage_scan() {
  local scan_output scan_rc outline_count semgrep_count evidence_count
  "$DISCOVERY_SCRIPTS/workspace.sh" --repo "$CHECKOUT" --json \
    >"$RUN_ROOT/payloads/workspace-v1.json" || return 1
  WORKSPACE="$(jq -er .workspace "$RUN_ROOT/payloads/workspace-v1.json")" || return 1
  scan_output="$($DISCOVERY_SCRIPTS/scan.sh --repo "$CHECKOUT")"
  scan_rc=$?
  printf '%s\n' "$scan_output"
  [ "$scan_rc" -eq 0 ] || return "$scan_rc"
  uat_scan_succeeded "$scan_output" || {
    printf 'error: aggregate scan did not finish with success\n' >&2
    return 1
  }
  printf '%s\n' "$scan_output" | sed -n 's/^run_id: //p' | tail -n 1 \
    >"$RUN_ROOT/payloads/scan-run-id.txt"
  [ -s "$RUN_ROOT/payloads/scan-run-id.txt" ] || return 1
  [ -f "$WORKSPACE/evidence/raw/ast-grep.jsonl" ] &&
    [ -f "$WORKSPACE/evidence/raw/semgrep.json" ] || return 1
  outline_count="$(grep -cve '^[[:space:]]*$' \
    "$WORKSPACE/evidence/raw/ast-grep.jsonl" || true)"
  semgrep_count="$(jq -er '.results | length' \
    "$WORKSPACE/evidence/raw/semgrep.json")" || return 1
  evidence_count=$((outline_count + semgrep_count))
  if [ "$evidence_count" -eq 0 ]; then
    printf 'error: scan produced no meaningful scanner evidence\n' >&2
    return 1
  fi
  jq -n \
    --arg run_id "$(cat "$RUN_ROOT/payloads/scan-run-id.txt")" \
    --arg workspace "$WORKSPACE" \
    --arg astgrep "$WORKSPACE/evidence/raw/ast-grep.jsonl" \
    --arg semgrep "$WORKSPACE/evidence/raw/semgrep.json" \
    --argjson astgrep_records "$outline_count" \
    --argjson semgrep_results "$semgrep_count" \
    '{run_id: $run_id, workspace: $workspace,
      evidence: {astgrep: $astgrep, semgrep: $semgrep,
        astgrep_records: $astgrep_records,
        semgrep_results: $semgrep_results}}' \
    >"$RUN_ROOT/payloads/scan.json"
}

stage_ingest() {
  local scan_run
  scan_run="$(cat "$RUN_ROOT/payloads/scan-run-id.txt")"
  "$TOOL_ENV/bin/python" -m archskillkit init --repo "$CHECKOUT" \
    >"$RUN_ROOT/payloads/init.json" || return 1
  "$TOOL_ENV/bin/python" -m archskillkit ingest-code --repo "$CHECKOUT" \
    --astgrep "$WORKSPACE/evidence/raw/ast-grep.jsonl" \
    --semgrep "$WORKSPACE/evidence/raw/semgrep.json" \
    --run-id "$scan_run" --scan-root "$CHECKOUT" \
    >"$RUN_ROOT/payloads/ingest.json" || return 1
  jq -e . "$RUN_ROOT/payloads/ingest.json" >/dev/null || return 1
  "$TOOL_ENV/bin/python" -m archskillkit index-stats --repo "$CHECKOUT" \
    >"$RUN_ROOT/payloads/index-stats.json" || return 1
  if ! jq -e '.files > 0 and (.symbols > 0 or .edges > 0)' \
    "$RUN_ROOT/payloads/index-stats.json" >/dev/null; then
    printf 'error: ingested code index is empty\n' >&2
    return 1
  fi
  jq . "$RUN_ROOT/payloads/index-stats.json"
}

stage_discover() {
  "$TOOL_ENV/bin/python" -m archskillkit discover --repo "$CHECKOUT" \
    --run-id "$(cat "$RUN_ROOT/payloads/scan-run-id.txt")" \
    >"$RUN_ROOT/payloads/discover.json" || return 1
  jq -e . "$RUN_ROOT/payloads/discover.json"
}

stage_review_drift() {
  "$TOOL_ENV/bin/python" -m archskillkit review --repo "$CHECKOUT" \
    >"$RUN_ROOT/payloads/review.json" || return 1
  "$TOOL_ENV/bin/python" -m archskillkit drift --repo "$CHECKOUT" \
    >"$RUN_ROOT/payloads/drift.json" || return 1
  jq -n \
    --slurpfile review "$RUN_ROOT/payloads/review.json" \
    --slurpfile drift "$RUN_ROOT/payloads/drift.json" \
    '{review: $review[0], drift: $drift[0]}' \
    >"$RUN_ROOT/payloads/review-drift.json"
  jq -e . "$RUN_ROOT/payloads/review-drift.json"
}

stage_project() {
  "$TOOL_ENV/bin/python" -m archskillkit project --repo "$CHECKOUT" \
    >"$RUN_ROOT/payloads/project.json" || return 1
  jq -e . "$RUN_ROOT/payloads/project.json"
}

stage_replay() {
  "$TOOL_ENV/bin/python" -m archskillkit replay-verify --repo "$CHECKOUT" \
    >"$RUN_ROOT/payloads/replay.txt"
}

stage_validate() {
  local model_rc build_rc=1 arrows_rc=0 metadata_rc=0 model_dir arrows_file
  local missing_fields arrows_count=0
  model_dir="$WORKSPACE/likec4"
  arrows_file="$WORKSPACE/arrows/architecture.arrows"

  "$DISCOVERY_SCRIPTS/model-validate.sh" --repo "$CHECKOUT"
  model_rc=$?
  if [ "$model_rc" -eq 0 ]; then
    # A successful static build proves the model compiles; it does not prove
    # that its visual layout is useful to a human.
    runtime_tool likec4 build "$model_dir" \
      --output "$RUN_ROOT/visual/likec4" --use-hash-history
    build_rc=$?
  fi

  missing_fields="$(jq -r '
    ["schema_version", "project_id", "root", "remote", "workspace", "commit"]
    - (keys) | join(",")' "$WORKSPACE/project.json" 2>/dev/null || printf invalid-json)"
  if [ -n "$missing_fields" ]; then
    metadata_rc=1
  fi

  if [ -f "$arrows_file" ]; then
    jq -e '
      .schema == "arch-skillkit/arrows-v1"
      and (.nodes | type == "array")
      and (.relationships | type == "array")
      and (([.nodes[].id] | length) == ([.nodes[].id] | unique | length))
      and ([.nodes[].id] as $ids
        | all(.relationships[]; (.start as $s | $ids | index($s)) != null
          and (.end as $e | $ids | index($e)) != null))' \
      "$arrows_file" >/dev/null || arrows_rc=1
    arrows_count=1
  else
    arrows_rc=1
  fi

  jq -n \
    --argjson model_valid "$([ "$model_rc" -eq 0 ] && printf true || printf false)" \
    --argjson static_build "$([ "$build_rc" -eq 0 ] && printf true || printf false)" \
    --arg build_path "$RUN_ROOT/visual/likec4" \
    --argjson arrows_valid "$([ "$arrows_rc" -eq 0 ] && printf true || printf false)" \
    --argjson arrows_files "$arrows_count" \
    --argjson metadata_valid "$([ "$metadata_rc" -eq 0 ] && printf true || printf false)" \
    --arg missing_fields "$missing_fields" \
    '{likec4: {valid: $model_valid, static_build: $static_build,
        build_path: $build_path, human_visual_review: "pending"},
      arrows: {valid: $arrows_valid, files_checked: $arrows_files,
        validation: "schema, unique node ids, relationship endpoints"},
      project_metadata: {valid: $metadata_valid,
        missing_required_fields: ($missing_fields | if length == 0 then [] else split(",") end)}}' \
    >"$RUN_ROOT/payloads/validation.json"
  jq . "$RUN_ROOT/payloads/validation.json"
  [ "$model_rc" -eq 0 ] && [ "$build_rc" -eq 0 ] &&
    [ "$arrows_rc" -eq 0 ] && [ "$metadata_rc" -eq 0 ]
}

stage_report() {
  local report_path report_rc
  "$DISCOVERY_SCRIPTS/report.sh" --repo "$CHECKOUT"
  report_rc=$?
  [ "$report_rc" -eq 0 ] || return "$report_rc"
  report_path="$WORKSPACE/reports/index.md"
  [ -f "$report_path" ] || return 1
  jq -n \
    --arg report "$report_path" \
    --arg sha256 "$(sha256sum "$report_path" | cut -d' ' -f1)" \
    --arg likec4_build "$RUN_ROOT/visual/likec4" \
    '{report: $report, sha256: $sha256,
      likec4_static_build: $likec4_build,
      human_visual_review: "pending"}' >"$RUN_ROOT/payloads/report.json"
}

prepare_checkout() {
  local config="$1" source_info normalized_remote
  source_info="$(find_local_source "$config")" || {
    uat_die "no local/cached source contains $TARGET_SHA; run 'just uat-fetch $TARGET_ID' (network) or set UAT_SOURCE_REPO"
    return 1
  }
  SOURCE_KIND="${source_info%%$'\t'*}"
  SOURCE_REPO="${source_info#*$'\t'}"

  if git -C "$SOURCE_REPO" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    uat_git_evidence "$SOURCE_REPO" >"$RUN_ROOT/evidence/source-before.json"
    SOURCE_BEFORE="$RUN_ROOT/evidence/source-before.json"
  fi

  CHECKOUT="$RUN_ROOT/work/checkout"
  git clone --quiet --no-checkout --no-hardlinks "$SOURCE_REPO" "$CHECKOUT" || return 1
  git -C "$CHECKOUT" checkout --quiet --detach "$TARGET_SHA" || return 1
  git -C "$CHECKOUT" remote set-url origin "$TARGET_REPOSITORY" || return 1
  [ "$(git -C "$CHECKOUT" rev-parse HEAD)" = "$TARGET_SHA" ] || {
    uat_die "ephemeral checkout did not resolve pinned SHA"
    return 1
  }
  normalized_remote="$(git -C "$CHECKOUT" remote get-url origin | sed -E 's#^https?://##; s#\.git$##')"
  [ "$normalized_remote" = "$(target_value "$config" normalized_remote)" ] || {
    uat_die "ephemeral checkout remote does not match target identity"
    return 1
  }
  [ -z "$(git -C "$CHECKOUT" status --porcelain=v1 --untracked-files=all)" ] || {
    uat_die "ephemeral checkout is not clean"
    return 1
  }
  uat_git_evidence "$CHECKOUT" >"$RUN_ROOT/evidence/checkout-before.json"
  CHECKOUT_BEFORE="$RUN_ROOT/evidence/checkout-before.json"
  chmod -R a-w -- "$CHECKOUT"
}

write_manifest() {
  local lock_present=false
  [ -f "$ROOT/devbox.lock" ] && lock_present=true
  jq -n \
    --argjson schema_version 1 \
    --arg run_id "$(basename "$RUN_ROOT")" \
    --arg target "$TARGET_ID" \
    --arg repository "$TARGET_REPOSITORY" \
    --arg commit "$TARGET_SHA" \
    --arg source_kind "$SOURCE_KIND" \
    --arg source_repo "$SOURCE_REPO" \
    --arg checkout "$CHECKOUT" \
    --arg artifact_root "$RUN_ROOT" \
    --arg created_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --arg lock_path "$ROOT/devbox.lock" \
    --argjson lock_present "$lock_present" \
    --slurpfile resource_limits "$RUN_ROOT/evidence/resource-limits.json" \
    '{schema_version: $schema_version, run_id: $run_id, target: $target,
      repository: $repository, commit: $commit,
      source: {kind: $source_kind, repo: $source_repo},
      ephemeral_checkout: $checkout, artifact_root: $artifact_root,
      created_at: $created_at,
      reproducibility: {
        devbox: {
          lock_path: $lock_path,
          lock_present: $lock_present,
          inputs_locked: $lock_present,
          package_realization: "may-download-locked-packages-before-runner-starts"
        },
        pipeline: {
          mise_auto_install: false,
          boundary: "runner-starts-after-devbox-environment-realization",
          resource_limits: $resource_limits[0]
        }
      }}' >"$RUN_ROOT/manifest.json"
}

run_uat() {
  local target="${1:-pipeline-kotlin}" config run_parent critical_failed=0 validation_failed=0 report_failed=0
  config="$(uat_resolve_target "$ROOT" "$target")" || return 2
  TARGET_ID="$(target_value "$config" id)"
  TARGET_SHA="$(target_value "$config" commit)"
  TARGET_REPOSITORY="$(target_value "$config" repository)"

  [ -x "$TOOL_ENV/bin/python" ] || {
    uat_die "cached Python environment missing; run 'just uat-bootstrap'"
    return 2
  }
  uat_require_tools bash git jq mise python uv sha256sum realpath sed tar || return 2

  run_parent="$UAT_STATE_BASE/runs"
  [ "$(realpath -m "$run_parent")" != / ] || return 2
  mkdir -p "$run_parent"
  RUN_ROOT="$(mktemp -d "$run_parent/${TARGET_ID}-$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")"
  mkdir -p "$RUN_ROOT"/{evidence,logs,payloads,stages,visual,work}
  trap on_run_exit EXIT
  trap 'exit 129' HUP
  trap 'exit 130' INT
  trap 'exit 143' TERM

  prepare_checkout "$config" || return 1

  export XDG_CONFIG_HOME="$RUN_ROOT/xdg/config"
  export XDG_DATA_HOME="$RUN_ROOT/xdg/data"
  export XDG_STATE_HOME="$RUN_ROOT/xdg/state"
  export XDG_CACHE_HOME="$RUN_ROOT/xdg/cache"
  export ARCH_SKILLKIT_HOME="$RUN_ROOT/xdg/data/arch-skillkit"
  export UV_CACHE_DIR="$UV_CACHE"
  uat_disable_runtime_downloads >/dev/null
  mkdir -p "$XDG_CONFIG_HOME" "$XDG_DATA_HOME" "$XDG_STATE_HOME" "$XDG_CACHE_HOME"

  capture_versions >"$RUN_ROOT/versions.json"
  capture_resource_limits >"$RUN_ROOT/evidence/resource-limits.json" || return 2
  write_manifest || return 1

  run_stage scan stage_scan || critical_failed=1
  if [ "$critical_failed" -eq 0 ]; then run_stage ingest stage_ingest || critical_failed=1; fi
  if [ "$critical_failed" -eq 0 ]; then run_stage discover stage_discover || critical_failed=1; fi
  if [ "$critical_failed" -eq 0 ]; then run_stage review-drift stage_review_drift || critical_failed=1; fi
  if [ "$critical_failed" -eq 0 ]; then run_stage project stage_project || critical_failed=1; fi
  if [ "$critical_failed" -eq 0 ]; then run_stage replay stage_replay || critical_failed=1; fi

  if [ "$critical_failed" -eq 0 ]; then
    run_stage validate stage_validate || validation_failed=1
    # Reporting still runs after a failed validation so the defect remains
    # inspectable instead of being hidden by early exit.
    run_stage report stage_report || report_failed=1
  fi

  if [ "$critical_failed" -ne 0 ]; then
    FINAL_STATUS="failed"
    FINAL_REASON="critical UAT stage failed"
    return 1
  fi
  if [ "$validation_failed" -ne 0 ] || [ "$report_failed" -ne 0 ]; then
    FINAL_STATUS="failed"
    FINAL_REASON="validation/report stage found a defect; inspect stage logs and validation.json"
    return 1
  fi
  FINAL_STATUS="passed"
  FINAL_REASON="all automated stages passed; human visual review remains pending"
  return 0
}

doctor() {
  local failed=0 tool
  printf 'Pure UAT toolchain\n'
  for tool in bash git jq mise python uv bats sha256sum realpath sed tar; do
    if command -v "$tool" >/dev/null 2>&1; then
      printf '  OK      %s\n' "$tool"
    else
      printf '  MISSING %s\n' "$tool"
      failed=1
    fi
  done
  if [ -x "$TOOL_ENV/bin/python" ] &&
    "$TOOL_ENV/bin/python" -c 'import archskillkit' >/dev/null 2>&1; then
    printf '  OK      cached archskillkit Python environment\n'
  else
    printf '  MISSING cached archskillkit environment (run: just uat-bootstrap)\n'
    failed=1
  fi
  for tool in ast-grep semgrep likec4; do
    if runtime_tool "$tool" --version >/dev/null 2>&1; then
      printf '  OK      %s (locked skill runtime)\n' "$tool"
    else
      printf '  MISSING %s (run: just uat-bootstrap)\n' "$tool"
      failed=1
    fi
  done
  printf '  INFO    Podman intentionally unused: this UAT has no service boundary.\n'
  return "$failed"
}

bootstrap() {
  mkdir -p "$UAT_CACHE_BASE/tooling"
  mise trust "$RUNTIME_DIR/mise.toml"
  mise install -C "$RUNTIME_DIR"
  UV_CACHE_DIR="$UV_CACHE" UV_PROJECT_ENVIRONMENT="$TOOL_ENV" \
    uv sync --project "$ROOT/python" --python "$(command -v python)" --extra dev --locked
  doctor
}

fetch_target() {
  local target="${1:-pipeline-kotlin}" config cache tmp sha repository rc=0
  config="$(uat_resolve_target "$ROOT" "$target")" || return 2
  sha="$(target_value "$config" commit)"
  repository="$(target_value "$config" repository)"
  cache="$(source_cache_path "$target")"
  mkdir -p "$SOURCE_CACHE"

  if [ -d "$cache" ]; then
    git --git-dir="$cache" remote set-url origin "$repository"
    git --git-dir="$cache" fetch --prune origin \
      '+refs/heads/*:refs/heads/*' '+refs/tags/*:refs/tags/*' || rc=$?
  else
    tmp="$SOURCE_CACHE/.${target}.fetch.$$"
    uat_safe_remove_dir "$SOURCE_CACHE" "$tmp"
    git clone --mirror "$repository" "$tmp" || rc=$?
    if [ "$rc" -eq 0 ]; then
      git --git-dir="$tmp" cat-file -e "$sha^{commit}" || rc=$?
    fi
    if [ "$rc" -eq 0 ]; then
      mv "$tmp" "$cache"
    else
      uat_safe_remove_dir "$SOURCE_CACHE" "$tmp"
    fi
  fi
  [ "$rc" -eq 0 ] || return "$rc"
  [ "$(git --git-dir="$cache" rev-parse "$sha^{commit}")" = "$sha" ] ||
    uat_die "cached repository does not contain exact commit $sha"
  printf 'cached target: %s\nverified commit: %s\n' "$cache" "$sha"
}

main() {
  case "${1:-}" in
    doctor) doctor ;;
    bootstrap) bootstrap ;;
    fetch) fetch_target "${2:-pipeline-kotlin}" ;;
    run) run_uat "${2:-pipeline-kotlin}" ;;
    -h | --help | help | '') usage ;;
    *) usage >&2; uat_die "unknown command: $1" ;;
  esac
}

if [ "${UAT_NO_MAIN:-0}" != 1 ]; then
  main "$@"
fi
