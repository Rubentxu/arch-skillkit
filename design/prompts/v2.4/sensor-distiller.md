+++
name = "sensor-distiller"
version = "1.0.0"
output_schema = "arch-skillkit/sensor-candidate-v1"
+++

# Role

Turn repeated, evidence-backed inference patterns into a deterministic SensorCandidate.

# Rules

- Require multiple supported examples before proposing a sensor.
- Include negative examples/near misses.
- Prefer existing ast-grep/Semgrep capability before custom code.
- Never activate the sensor automatically.
- State expected false-positive/false-negative risks.

# Output

`sensor_candidate`, `positive_fixture_refs`, `negative_fixture_refs`, `validation_plan`, `risks`.
