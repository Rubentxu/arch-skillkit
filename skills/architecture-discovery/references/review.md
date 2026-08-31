# Review Role

Audits the inventory, the model and the process. The Review role questions;
it never invents and never repairs silently.

## Checks

Run, in order:

1. **Evidence audit** — every `high` confidence claim cites evidence. A
   relationship without evidence is NEVER promoted to `high`: mark it,
   downgrade it, or exclude it (UAT-005).
2. **Contradictions** — evidence conflicting with the existing model or with
   another piece of evidence becomes a finding; never resolve it silently.
3. **Duplicates** — the same relationship reported twice.
4. **Orphans** — elements with no relationships and no purpose note.
5. **Over-modeling** — functions, classes or imports that belong in evidence,
   not in the architecture model.
6. **Repository cleanliness** — `git status --porcelain` identical before and
   after the workflow (UAT-001). Any difference is a blocking finding.
7. **Manifest coherence** — the run manifest records the scanners that
   actually ran; `partial` runs list which capability degraded.

## Output contract

Write `reports/review-findings.md`:

```markdown
# Review findings

- F-001 [blocking] relationship OrdersService -> Stripe has no evidence — downgraded to low, moved to assumptions
- F-002 [warning] duplicate edge orders -> billing reported by outline and patterns — deduplicated
- F-003 [info] PaymentEvents has no incoming relationships — kept, listener evidence exists
```

Severity:

- `blocking` — evidence missing on a high claim, repository dirtied, model
  invalid. The workflow is not done until resolved.
- `warning` — contradiction, duplicate, over-modeling.
- `info` — observations worth keeping.

The Review role does not fix findings itself: it records them and hands them
back to the Modeler/Discovery roles or to the human.
