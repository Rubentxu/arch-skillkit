# Audit Report — ActiveGraph Closure (M3)

## Status

**Accepted** — M3 acceptance gates (ARCH-ACTIVEGRAPH-001, ARCH-GRAPH-LEAK-001)
are PASS as of v0.14.0. No new code is required.

## Context

V2.5 roadmap Milestone M3 ("ActiveGraph Boundary & Ports") declares two
acceptance gates in `docs/v2/84-v2.5-milestones.md`:

- `ARCH-ACTIVEGRAPH-001` — ActiveGraph outbound adapter exists
- `ARCH-GRAPH-LEAK-001` — `world.graph` leakage eliminated

These gates are enforced by the architecture verifier rules in
`docs/v2/verification/architecture-contracts.json`:

- **ARC-003**: `forbidden_import_prefix: ["activegraph"]` in `scope: ["application"]`
- **ARC-006**: `forbidden_attribute: "graph"` in `scope: ["."]`, with allow list for the adapter path

This audit collects the evidence that both rules pass at v0.14.0.

## Evidence

### 1. ActiveGraph import inventory

`grep -rn "from activegraph\|import activegraph" python/src/archskillkit/`:

| Path | Line | Statement | Classification |
|---|---|---|---|
| `python/src/archskillkit/world.py` | 19 | `from activegraph import Graph, Runtime` | Adapter boundary (allowed by ADR-0024) |
| `python/src/archskillkit/world.py` | 20 | `from activegraph.store import open_store` | Adapter boundary |
| `python/src/archskillkit/world.py` | 285 | `from activegraph.store import open_store` | Lazy import inside adapter boundary |
| `python/src/archskillkit/world.py` | 286 | `from activegraph.store.sqlite import SQLiteEventStore` | Lazy import inside adapter boundary |
| `python/src/archskillkit/packs/arch_core.py` | 19 | `from activegraph.packs import ObjectType, Pack, RelationType` | Type imports for pack definitions (legitimate) |
| `python/src/archskillkit/packs/arch_model.py` | 16 | `from activegraph.packs import ObjectType, Pack, RelationType` | Type imports for pack definitions (legitimate) |

The contract's allow list mentions `adapters/outbound/activegraph/` as the
logical adapter path; in practice the adapter is split across `world.py`
(the runtime facade) and `repositories.py` (the repository contracts that
hide ActiveGraph calls). The `packs/arch_*.py` modules only consume public
types from `activegraph.packs` and do not invoke any ActiveGraph runtime
internals.

### 2. ARC-003 enforcement (application/)

`grep -rn "^import activegraph\|^from activegraph" python/src/archskillkit/application/`:
**0 matches.**

### 3. ARC-006 enforcement (`world.graph` access)

Manual audit of `.graph` attribute access in `python/src/archskillkit/`:

- All matches found are either:
  - Docstring/comment text referencing the conceptual boundary (e.g. "never `world.graph` outside the domain boundary")
  - JavaScript-style snippets in `delivery/cli/control_plane.py` (TypeScript template literals, not Python AST nodes)
- **0 real `world.graph` attribute accesses outside the allow list.**

### 4. Verifier output

`python docs/v2/verification/arch_conformance.py --root python/src/archskillkit --contracts docs/v2/verification/architecture-contracts.json`:

```
exit_code: 0
checks:
  ARC-010: count=0
  mixed: count=5 (ARC-002 TYPE_CHECKING delivery imports × 2, ARC-004 TYPE_CHECKING world imports × 3 — pre-existing baseline)
  APP-COVERAGE-001: ratio=1.0
```

ARC-003 and ARC-006 emit 0 findings (consumed by the `mixed` bucket if any
violation existed; both are empty).

### 5. Architecture diagram

```
┌─────────────────────────────────────────┐
│  delivery/ (cli, mcp, http, viewers)    │ — no activegraph imports
└──────────────────┬──────────────────────┘
                   │ uses
                   ▼
┌─────────────────────────────────────────┐
│  application/ (commands, queries, ports)│ — ARC-003 enforced (0)
└──────────────────┬──────────────────────┘
                   │ uses
                   ▼
┌─────────────────────────────────────────┐
│  bootstrap/__init__.py                  │
│  ArchSkillKitApplication (composition   │
│  root)                                  │
└──────────────────┬──────────────────────┘
                   │ owns
                   ▼
┌─────────────────────────────────────────┐
│  world.py + repositories.py             │ — ARC-006 enforced (0)
│  ── ActiveGraph adapter boundary ──     │
│  from activegraph import Graph, Runtime │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│  activegraph (external library)         │
│  + activegraph.sqlite (per-project)     │
└─────────────────────────────────────────┘
```

## Decision

M3 is **closed**. The acceptance gates are satisfied by prior cycles:

- v0.9.0 baseline calibrated the verifier (ARC-003 and ARC-006 in
  `architecture-contracts.json`).
- v0.10.0 cherry-pick established the composition root, ensuring
  `ArchSkillKitApplication` is the single owner of `ArchitectureWorld`.
- v0.12.0 APP-COVERAGE 1.0 confirmed all governance paths route through the
  application layer (where ARC-003 forbids ActiveGraph imports).
- v0.13.0 M5 codegraph port refactor moved code intelligence behind a port,
  parallel to the ActiveGraph adapter pattern.
- v0.14.0 M5 closure consolidated provider SPI documentation.

The "ActiveGraph outbound adapter" deliverable from M3 is physically
realized as `world.py` + `repositories.py`. The contract rule ARC-006 names
the logical path `adapters/outbound/activegraph/`; the audit confirms the
physical implementation is equivalent.

## Consequences

- The V2.5 roadmap M3 entry can move from "in progress" to "closed" once
  this audit is linked from `docs/v2/84-v2.5-milestones.md`.
- No code changes are required to satisfy the M3 exit criteria.
- Future migrations of the underlying graph library (e.g. from ActiveGraph
  to a different event-sourced store) will be localized to
  `world.py` + `repositories.py` — application and delivery code will not
  need to change.

## Verification commands

```bash
# Reproduce ARC-003 evidence
grep -rn "^import activegraph\|^from activegraph" python/src/archskillkit/application/

# Reproduce ARC-006 evidence
grep -rn '\.graph\b' python/src/archskillkit/ --include="*.py" \
  | grep -v 'codegraph\|test_\|codeindex\|__pycache__\|world.py\|repositories.py\|adapters/outbound/activegraph'

# Reproduce verifier output
python docs/v2/verification/arch_conformance.py \
  --root python/src/archskillkit \
  --contracts docs/v2/verification/architecture-contracts.json
```
