# Doctor coverage (M1.2): read-only environment verification.
# Seam: doctor.sh CLI — exit code and report; it must not create anything.
load 'test_helper'

setup() {
  new_sandbox
}

@test "doctor reports the resolved roots" {
  run run_doctor
  assert_output_contains "roots section present" "resolved roots" "$output"
  assert_output_contains "config root present" "arch-skillkit" "$output"
}

@test "doctor exits 1 when required tools are missing" {
  run run_doctor "$SB/emptybin"
  assert_rc "missing required tools fail" 1 "$status"
  assert_output_contains "names the missing dependency" "MISSING" "$output"
}

@test "doctor is read-only: no workspace or state is created" {
  run run_doctor
  [ "$status" -eq 0 ] || [ "$status" -eq 1 ]
  [ ! -e "$SB/data/arch-skillkit/projects" ]
  [ ! -e "$SB/state/arch-skillkit/registry.json" ]
}
