# Modeler Role (LikeC4)

Owns the canonical architecture model. The Modeler translates the inventory
into LikeC4 conservatively and keeps it valid.

## Inputs

- `reports/inventory.md` (Discovery) — claims with origin and evidence.
- `knowledge/overrides.yaml` (DECLARED).
- The existing model, if any: `likec4/model.c4`.

## Procedure

1. If `likec4/model.c4` does not exist, start from
   `templates/model.c4` (validates by construction) — never from an empty
   file.
2. Edit the model following `references/modeling-policy.md`: systems,
   containers, architecturally significant components, external systems,
   datastores, messaging. Do not model every symbol.
3. Mark every element and relationship with origin and confidence tags:

   ```likec4
   api = container 'API' {
     #detected #confidence-high
   }
   a -> b 'calls' {
     #inferred #confidence-medium
     link ../../evidence/raw/semgrep.json 'evidence'
   }
   ```

   `link` points at the evidence file inside the project workspace (OQ-04
   resolution: tags carry origin/confidence, links carry evidence — the
   likec4 1.59 `metadata` block is reserved for free-form annotations).
4. Keep the views useful: at least `context` and `containers`.
5. Validate: `scripts/model-validate.sh`. An invalid model is not done —
   fix and re-validate. The pipeline must never commit an invalid model,
   and the last valid model is never overwritten (docs/23).

## Conservative update (M4.2, UAT-006)

- Re-runs never start from scratch: edit the existing model, do not
  regenerate it.
- DECLARED knowledge (from overrides) is never deleted unless the human
  instruction says so.
- When new scanner evidence contradicts the model, do not fix silently:
  produce a review finding (references/review.md) and adjust only what the
  evidence supports.
- Elements whose supporting evidence disappeared are marked obsolete
  (`#inferred #confidence-low` plus a description note), never deleted
  without a review finding.
- Model changes must be explainable: each edit answers "which evidence or
  declaration moved this?".
