# V2.4 M5 Slice 23a — draw.io embed XML round-trip / metadata proof

**Gate**: blocking experiment for slice 23 (draw.io semantic edit → proposal
candidate). **Status: PASS** (deterministic, reproducible; see Exit Criteria).

---

## Protocol Reference

Official docs: https://www.drawio.com/doc/faq/embed-mode

```
iframe: https://embed.diagrams.net/?embed=1&proto=json...
handshake: {event:'init'} → host {action:'load', xml} → host {action:'export', format:'xml'}
response:  {event:'export', format:'xml', xml:'...'}
```

**Critical constraints (enforced in harness + page)**:
- `postMessage` target MUST be exactly `https://embed.diagrams.net` (never `*`).
- Receive listener MUST accept exactly `https://embed.diagrams.net`.
- Edit flow uses ONLY official protocol actions (`load`, `merge`, `export`).

---

## Empirical rules (PROVEN by this experiment — do not re-derive)

These rules were established against real embed.diagrams.net output
(drawio 31.4.2, chromium headless, Sep 2026) and are the foundation for
the slice-23 classifier design:

| # | Rule | Evidence |
|---|------|----------|
| R1 | `export format=json` does NOT carry semantic cells/metadata (returned only `{id:'1',type:'layer'}` for a 6-cell diagram). JSON route REJECTED. | `fixtures/drawio-json-export-NEGATIVE.fixture.json` |
| R2 | XML attribute names containing `/` are INVALID XML (`arch-skillkit/x` → ElementTree ParseError). Valid keys: `archskillkit-element-name`, `archskillkit-element-kind`, `archskillkit-relation-kind`, `archskillkit-relation-source-name`, `archskillkit-relation-target-name`. | `fixtures/drawio-xml-parse-ERROR.trace.txt` |
| R3 | `load` UNWRAPS `UserObject` vertices and DROPS custom attributes (vertices arrive as plain `mxCell` with only the visible `value`). Flat `mxCell` edge attributes DO survive `load`. | first load-flow run, criterion 5 failure |
| R4 | `merge` with a full `<mxfile>` whose page id matches an existing page REPLACES that page through a stripping import path (UserObject metadata LOST). | merge#2-with-mxfile run (criteria 7/8/9 fail) |
| R5 | `merge` with a NEW page id (or a bare `<mxGraphModel>`) PRESERVES `UserObject` + custom attributes through export. The correct production channel: `load(blank) → merge(artifact as mxGraphModel) → …human edits… → export`. | final PASS run, criteria 5–9 |
| R6 | Successive `merge` calls replace the CURRENT page content (merge is not an incremental patch): the host composes the FULL new state (saved model + edit) and merges it wholesale. | merge#1-fragment run (artifact vanished) |
| R7 | `export` is deterministic for identical model state once draw.io's random `<diagram id>` session randomness is canonicalized. | RUN1==RUN2 canonical sha `34a7d186…` across 3 independent invocations |
| R8 | The `load(blank) → merge(...)` flow leaves a leading EMPTY page named `Página-1` in exports. It is noise; the classifier must ignore pages without archskillkit cells (canonicalization may later strip it in the adapter). | final fixture: `diagram[0]` empty |

**Production flow implied by R3–R6** (for slice 23b+ design):
`load(blank) → merge(artifact-as-mxGraphModel)` initializes the editor with
metadata intact; the host composes full-state merges for programmatic
edits; `export(format=xml)` returns metadata-preserving XML.

---

## Metadata Encoding (XML-valid)

Vertices (elements) — `UserObject` wrapper:

```xml
<UserObject id="n0" label="TestService · component · DETECTED/high"
            archskillkit-element-name="TestService"
            archskillkit-element-kind="component">
  <mxCell vertex="1" parent="1" value="TestService · component · DETECTED/high" style="…">
    <mxGeometry x="0" y="0" width="180" height="60" as="geometry" />
  </mxCell>
</UserObject>
```

Edges (relations) — flat `mxCell`:

```xml
<mxCell id="e0" value="calls" style="…" edge="1" parent="1"
        source="n0" target="n1"
        archskillkit-relation-kind="calls"
        archskillkit-relation-source-name="TestService"
        archskillkit-relation-target-name="TestDatabase">
  <mxGeometry relative="1" as="geometry" />
</mxCell>
```

NEVER parse `value`/`label` to recover semantics — presentation only.

---

## Test Harness

**`scripts/uat/m5-slice-23a/generate-roundtrip-page.py`** — stdlib-only;
generates the self-contained proof page + a `.drawio` fixture with the
XML-valid metadata encoding. Page flow:
`load(blank) → merge(artifact) → export(base) → merge(base+n_roundtrip) → export(edited)`.

**`scripts/uat/m5-slice-23a/verify-drawio-xml-roundtrip.mjs`** — Playwright
1.62.1 headless chromium, TWO consecutive full runs (RUN1, RUN2):
1. Waits for `init` from EXACT origin.
2. Drives the 5-step page flow via native button clicks + PHASE markers.
3. Captures exports via an `addInitScript` interceptor (exact-origin gated).
4. Saves the edited re-export as the classifier fixture (+ `.base.xml`
   sibling, + raw-sha sidecars).
5. Determinism: canonical sha256 (diagram page ids normalized) must match
   across RUN1/RUN2; sidecar = sha of the raw file.

---

## Exit Criteria (all PASS)

| # | Criterion |
|---|-----------|
| 1 | Real embed-mode XML export captured from exact origin `https://embed.diagrams.net` (both runs) |
| 2/3 | ElementTree-compatible XML (verified in Python via `test_drawio_delta.py`) |
| 4 | Deterministic canonical sha256: RUN1 == RUN2 (`34a7d186d54e06645899107b46f7f3c05924e5b44bf2eaed9b3e3e9ac36fdaab`) |
| 5/6 | Base export: 3 UserObject vertices + 2 edges with archskillkit metadata |
| 7 | Re-export contains `n_roundtrip` with `archskillkit-element-name="new-svc"`, `archskillkit-element-kind="component"` |
| 8 | drawio produces UserObject-wrapped vertex encoding on the merge channel |
| 9 | Re-export carries the FULL edited model: 4 metadata vertices + 2 metadata edges (edit did not destroy base) |

Negative evidence preserved:
`fixtures/drawio-json-export-NEGATIVE.fixture.json` (+ `.notes.md`) and
`fixtures/drawio-xml-parse-ERROR.trace.txt`.

---

## Run Command

```bash
# Regenerate the proof page + drawio fixture
python3 scripts/uat/m5-slice-23a/generate-roundtrip-page.py \
  --out artifacts/uat/v2.4/m5-slice-23a/drawio-xml-roundtrip-proof.html \
  --drawio-out artifacts/uat/v2.4/m5-slice-23a/test-xml-metadata.drawio

# Run the two-run Playwright verification (Playwright is NOT a repo dep)
npm i --prefix /tmp/opencode playwright@1.62.1
PLAYWRIGHT_NM=/tmp/opencode/node_modules/ \
  node scripts/uat/m5-slice-23a/verify-drawio-xml-roundtrip.mjs
# Exit 0 = PASS · Exit 1 = FAIL · Exit 2 = BLOCKED (browser/network)
```

Python-side consumability: `python/tests/test_drawio_delta.py` (loads the
captured RUN1 fixture, parses with ElementTree, extracts metadata).
