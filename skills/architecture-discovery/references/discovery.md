# Discovery Role

Reads the evidence bundle and produces the architectural inventory. The
Discovery role interprets; it never scans and never mutates anything.

## Inputs

- `evidence/raw/ast-grep.jsonl` — structural outline (DETECTED).
- `evidence/raw/semgrep.json` — architectural pattern matches (DETECTED).
- `evidence/raw/build/` — build-system metadata (DETECTED).
- `knowledge/overrides.yaml` — human declarations (DECLARED).

## Reading policy

Prefer, in order:

```text
evidence → targeted read → inference
```

Open source files ONLY when the evidence is ambiguous, contradictory, or a
boundary cannot be resolved without business context. Every targeted read
must be justified in the inventory: what question does it answer? Browsing
the repository recursively is never acceptable.

## Output contract

Write `reports/inventory.md` with one section per dimension:

- `## Systems` — systems and containers, each with a one-line purpose.
- `## Integrations` — external systems consumed or exposed.
- `## Datastores` — databases and stores.
- `## Messaging` — queues, topics, streams.
- `## Uncertainties` — open questions that evidence could not resolve.

Every claim line must carry its origin and evidence reference:

```text
- PaymentController exposes POST /payments [DETECTED, high] — semgrep.json: spring.endpoint
```

Rules:

- `DETECTED` claims cite the evidence file (and check_id/ruleId when present).
- `INFERRED` claims state confidence `medium` or `low` and name the
  supporting evidence; if none exists, they are uncertainties instead.
- `DECLARED` claims cite `knowledge/overrides.yaml`.
- Never present an inference as a detected fact.

Claims that are plausible but unverified move to `knowledge/assumptions.yaml`
using the declaration schema from `examples/overrides.yaml`, with confidence
`low` — they stay assumptions until validated (UAT-005: they must never be
promoted silently).
