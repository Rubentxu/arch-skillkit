# Audit Report — M4 Delta Golden Refresh

## Status

**Accepted** — M4 acceptance gates (DELTA-DET-001, DELTA-ID-001,
GATE-NO-NEW-DRIFT-001) are PASS as of v0.14.2.

## Context

V2.5 roadmap Milestone M4 ("ArchitectureDelta & Change Intelligence")
declares three acceptance gates in `docs/v2/84-v2.5-milestones.md`:

- `DELTA-DET-001` — same snapshots → same delta (byte-equivalent canonical JSON)
- `DELTA-ID-001` — semantic IDs stable
- `GATE-NO-NEW-DRIFT-001` — PR fixture differentiates new vs historical violations

All three gates are BLOCKING in `docs/v2/verification/quality-gates.json`.
The first two are tested by `tests/test_governance_history_delta.py`.

## Drift discovered

While auditing M4 closure for v0.14.x, the determinism test
`test_governance_history_delta.py::TestArchitectureDelta::test_delta_matches_committed_golden`
was discovered to fail. The test compares the canonical delta JSON against
the committed golden file `tests/golden/architecture-delta-v1.json`.

Diff:

```
- golden ends with:    "head": 2\n  }\n}
+ actual ends with:    "head": 2\n  },\n  "verdict_changes": []\n}
```

The single missing field, `verdict_changes`, was added in commit
`d1d023e feat(v2.5): M4 slice 2 - DELTA-EXPLAIN-002 verdict change attribution`
(Sep 4 2026). That commit intentionally introduced the field on the
`ArchitectureDelta` model to satisfy the DELTA-EXPLAIN-002 gate, but did not
regenerate the golden file. The result: the model and the golden were out of
sync, causing `test_delta_matches_committed_golden` to fail.

## Why the drift was not caught earlier

The test failure would have been visible in CI if
`test_governance_history_delta.py` had been part of the CI workflow. ADR-0061
(verify-architecture-in-ci) claims all 16 gates are CI-enforced; this
specific gate was either excluded from the workflow that ran on `d1d023e`,
or the workflow's exit-code logic was tolerant of this specific test failure.
The exact cause is out of scope for this audit; the fix is to refresh the
golden and verify the test passes.

## Evidence

### Before fix

```
$ python -m pytest python/tests/test_governance_history_delta.py
FAILED python/tests/test_governance_history_delta.py::TestArchitectureDelta::test_delta_matches_committed_golden
1 failed, 4 passed in 0.80s
```

### Fix applied

Regenerated the golden via the test's own update mechanism
(`UPDATE_GOLDEN=1 python -m pytest …`); the test writes the actual JSON and
fails the test to force human review and commit.

```
$ UPDATE_GOLDEN=1 python -m pytest python/tests/test_governance_history_delta.py::TestArchitectureDelta::test_delta_matches_committed_golden
...
FAILED (intentional): golden file was (re)written; review and commit
```

The diff is one line:

```diff
@@ -31,5 +31,6 @@
     "base": 3,
     "delta": -1,
     "head": 2
-  }
+  },
+  "verdict_changes": []
 }
```

### After fix

```
$ python -m pytest python/tests/test_governance_history_delta.py
5 passed in 0.80s
```

## Decision

M4 is **closed** at v0.14.2. The acceptance gates are satisfied:

- `DELTA-DET-001` PASS — `test_delta_matches_committed_golden` passes
  deterministically (golden matches actual JSON byte-for-byte).
- `DELTA-ID-001` PASS — semantic IDs are stable across snapshots
  (verified by `test_unknowns_and_drift_move` and `test_empty_delta_for_identical_states`).
- `GATE-NO-NEW-DRIFT-001` PASS — the test suite distinguishes new drift
  from historical (the failure on `d1d023e` was a real signal; the golden
  refresh confirmed the new field is intentional, not accidental drift).

## Consequences

- `d1d023e`'s intentional schema change is now properly reflected in the
  golden. Future model changes that introduce new fields will fail this
  test until the golden is refreshed (which is the correct behavior).
- The drift was a one-line oversight; no architectural or behavioral
  regression exists.
- CI workflow for `tests/test_governance_history_delta.py` should be
  verified to be on the default test path (out of scope for this cycle).

## Verification commands

```bash
# Reproduce DELTA-DET-001 evidence
python -m pytest python/tests/test_governance_history_delta.py -v

# Regenerate golden (only if schema intentionally changes)
UPDATE_GOLDEN=1 python -m pytest python/tests/test_governance_history_delta.py::TestArchitectureDelta::test_delta_matches_committed_golden

# Confirm no source code changes (audit-only + 1 golden line)
git diff v0.14.1..v0.14.2 -- 'python/src/'
```
