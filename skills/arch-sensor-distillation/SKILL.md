---
name: arch-sensor-distillation
description: Convert repeated evidence-backed LLM discoveries into deterministic ast-grep/Semgrep sensor candidates with positive and negative fixtures, tests and UAT. Use only when the same inference pattern recurs and deterministic detection would reduce cost or improve reproducibility.
---

# Sensor Distillation

## Preconditions

- repeated candidate pattern;
- supporting evidence from multiple examples;
- stable semantic target;
- measurable benefit.

## Workflow

```text
collect examples
 -> define semantic observation
 -> positives + negatives
 -> choose ast-grep/Semgrep
 -> author candidate rule
 -> unit fixtures
 -> OSS/UAT
 -> review SensorPackRevision
```

## Gate

Never enable a generated rule because it “looks correct”. Precision/recall and regressions must be measured.
