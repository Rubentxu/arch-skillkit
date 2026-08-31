# LikeC4 model coverage (M4.1/M4.2): validation and conservative updates.
# Seam: model-validate.sh CLI — exit code and report; it must not modify
# anything. UAT-006 seed: re-runs never touch knowledge/ or likec4/.
load 'test_helper'

setup() {
  new_sandbox
  make_fixture_repo "$SB/repo" rust-hexagonal
  local pid
  pid="$(jq -r --arg root "$SB/repo" '.projects[] | select(.root == $root) | .project_id' "$SB/state/arch-skillkit/registry.json")"
  MODEL_WS="$SB/data/arch-skillkit/projects/$pid"
  mkdir -p "$MODEL_WS/likec4" "$MODEL_WS/knowledge"
}

@test "model: golden template validates" {
  cp "$SCRIPTS/../templates/model.c4" "$MODEL_WS/likec4/model.c4"
  run run_model_validate "$SB/repo"
  [ "$status" -eq 0 ]
  assert_output_contains "valid model reported" "Valid" "$output"
}

@test "model: broken model fails with an actionable error and is left untouched" {
  printf 'model {\n  broken = element_with_typo %sX%s\n}\n' "'" "'" >"$MODEL_WS/likec4/model.c4"
  local checksum
  checksum="$(sha256sum "$MODEL_WS/likec4/model.c4")"
  run run_model_validate "$SB/repo"
  assert_rc "broken model rejected" 1 "$status"
  assert_output_contains "error names the file" "model.c4" "$output"
  assert_eq "model untouched by validation" "$checksum" "$(sha256sum "$MODEL_WS/likec4/model.c4")"
}

@test "model: workspace without model is a no-op, not an error" {
  run run_model_validate "$SB/repo"
  [ "$status" -eq 0 ]
  assert_output_contains "reports nothing to validate" "no model" "$output"
}

@test "model: rerun does not touch likec4/ or knowledge/ (UAT-006 seed)" {
  cp "$SCRIPTS/../templates/model.c4" "$MODEL_WS/likec4/model.c4"
  printf 'declarations:\n  - subject: api\n    predicate: belongs_to\n    object: commerce\n    confidence: high\n' >"$MODEL_WS/knowledge/overrides.yaml"
  local model_before knowledge_before
  model_before="$(sha256sum "$MODEL_WS/likec4/model.c4")"
  knowledge_before="$(sha256sum "$MODEL_WS/knowledge/overrides.yaml")"

  run run_scan_all "$SB/repo"
  [ "$status" -eq 0 ]

  assert_eq "model preserved across reruns" "$model_before" "$(sha256sum "$MODEL_WS/likec4/model.c4")"
  assert_eq "overrides preserved across reruns" "$knowledge_before" "$(sha256sum "$MODEL_WS/knowledge/overrides.yaml")"
}
