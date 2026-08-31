# Scanner Output Interpretation

How to read the raw evidence the deterministic pipeline produces. These
are the actual formats on disk, observed with the pinned toolchain —
not generic documentation. Read this before interpreting backend code
from scan results, and always prefer the Code Index queries
(`python -m archskillkit search-code`) over re-parsing raw payloads.

## ast-grep outline (`evidence/raw/ast-grep.jsonl`)

One JSON object per line per match, produced by
`ast-grep scan -c <sgconfig> --json=stream <repo>`:

```json
{
  "ruleId": "outline.kotlin.function",
  "text": "getPayment",
  "file": "/abs/path/Http.kt",
  "range": {"start": {"line": 11, "column": 4}, "end": {"line": 11, "column": 14}},
  "lines": "    fun getPayment(id: Long): Payment",
  "language": "Kotlin",
  "metaVariables": {"single": {}, "multi": {}}
}
```

Field semantics that matter:

- `ruleId` is `<pack>.<language>.<kind>` — the kind suffix
  (`function`, `type`, `struct`, `enum`, `trait`, `class`, `interface`)
  is what the Code Index stores as the symbol kind.
- `range.start.line` is **0-based**; the Code Index and every report
  surface 1-based lines. Never mix the two when pointing an agent at a
  source location.
- `text` is the selector capture (the symbol name), while `lines` is the
  full matched source line — use `lines` for signature context, `text`
  for identity.
- `file` is absolute as scanned; the Code Index relativizes it against
  the scan root.
- Repeated names in one file are normal (interface method + impl): two
  records, two symbols, distinguished by line.

## Semgrep patterns (`evidence/raw/semgrep.json`)

`semgrep scan --json` document:

```json
{
  "results": [{
    "check_id": "spring.endpoint",
    "path": "src/main/kotlin/demo/infra/Http.kt",
    "start": {"line": 11, "col": 1}, "end": {"line": 12, "col": 30},
    "extra": {"message": "HTTP endpoint declared ...",
              "metavars": {}, "lines": "requires login",
              "severity": "INFORMATION"}
  }]
}
```

Field semantics and traps:

- `check_id` is the rule id. With `--no-rewrite-rule-ids` it is bare
  (`spring.endpoint`); without it the OSS CLI prefixes the config path —
  our pipeline always passes the flag, so downstream code may assume
  bare ids.
- `start.line` is **1-based** (opposite of ast-grep). An annotation
  match (`@GetMapping(...)`) usually lands on the line just above the
  declaration: to find the handler symbol, the Code Index resolves the
  nearest declaration within ±2 lines, preferring functions.
- `extra.lines` is gated in OSS runs and may literally say
  `"requires login"`. Never treat it as source text; get context from
  the Code Index (`search-code`, or the context compiler's snippets,
  which read the real source at resolved locations).
- `extra.metavars` is `{}` unless a rule binds variables. When present,
  `abstract_content` carries the captured text (e.g. a route literal) —
  the Code Index uses it to name endpoint targets, falling back to
  positional names (`endpoint@11`).
- Architecture check-id families and their meaning:
  `*.endpoint` → the declaration EXPOSES an interface;
  `*.messaging.listener` → CONSUMES a topic;
  `*.persistence.repository` → USES a datastore;
  `http.client.*` → USES an external HTTP dependency.

## From raw evidence to architecture meaning

1. Symbols (ast-grep) answer **what exists** — files, types, functions.
2. Pattern matches (Semgrep) answer **what role a symbol plays** —
   endpoint handler, topic consumer, persistence port, HTTP client.
3. The Code Index joins both into edges (`EXPOSES`, `CONSUMES`, `USES`)
   with the rule as provenance; the promotion pipeline elevates them to
   Observations → Claims → architecture relations with evidence links.
4. When asked about a backend behaviour, do not re-read source first:
   query the index (`search-code`, `state`, `context`) and open source
   only at the resolved snippet locations (UAT2-008).
