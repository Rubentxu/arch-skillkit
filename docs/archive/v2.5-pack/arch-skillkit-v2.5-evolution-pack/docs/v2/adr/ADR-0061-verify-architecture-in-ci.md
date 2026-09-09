# ADR-0061 — `verify:architecture` in CI + Lazy MCP Import Guard

Status: Proposed

## Context

The `mise run ci` aggregator does not currently invoke architecture conformance verification. The `arch_conformance.py` tool exists and can enforce ARC-002, ARC-004, ARC-005, and (with this cycle) ARC-010, but it is not run as part of the standard CI pipeline. Additionally, `delivery/cli/mcp.py` has a top-level unconditional `from mcp.server import Server` import (line 27) that causes `archskillkit` to fail on import when the `mcp` extra is not installed.

The v2.5 alignment cycle extends `ADR-0009-reproducible-contributor-entry-point` (mise as canonical entry point) by adding `verify:architecture` to the `mise run ci` aggregator and implementing the lazy MCP import guard.

## Decision

### CI Integration

`mise.toml[tasks.ci]` is updated: `depends = ["lint", "test:python", "test:bats", "verify:architecture"]`. A new `[tasks."verify:architecture"]` block is added that delegates to `arch_conformance.py`.

CI fails on:
- (a) Any `new_findings` from `arch_conformance.py` against `architecture-baseline.json`.
- (b) `APP-COVERAGE-001` < 0.9 (per the liberal formula in ADR-0060).
- (c) Any new `ARC-002/004/005/010` hit.

### Lazy MCP Import Guard

`delivery/cli/mcp.py` implements a lazy import guard: the top-level `from mcp.server import Server` (and sibling imports) is moved inside the `register()` function. When `mcp` is not installed, the import raises `click.ClickException("Install archskillkit[mcp] to use the MCP server")`.

This allows `archskillkit` to be installed without the `[mcp]` extra and still load correctly. The MCP server registration requires the extra; other CLI commands work without it.

## Decision Table

| # | Alternative | Why not chosen |
|---|-------------|----------------|
| 1 | **Add `verify:architecture` to `mise run ci`; fold in lazy MCP import guard; fail on (a) (b) (c)** (CHOSEN) | n/a |
| 2 | Run `verify:architecture` only on release tag | Allows the baseline to decay between releases (the M0 baseline exists *because* the verifier ran) |
| 3 | Defer lazy MCP import to a separate cycle | Mechanical and orthogonal; bundling saves a sub-cycle |

## Consequences

Positive:
- Architecture conformance is now enforced on every CI run.
- `archskillkit` works without the `mcp` extra.
- The lazy import guard is a minimal, isolated change.

Negative:
- CI now has a additional step that could block merges — the baseline must remain clean.
- Any new `arch_conformance.py` finding against baseline blocks the merge (this is the intended gate behaviour).

## Trade-offs

Running `verify:architecture` only on release tags would allow baseline decay between releases. The cost of the CI step (additional runtime) is lower than the benefit (continuous conformance enforcement). The lazy MCP import is bundled into this ADR because it is a small, orthogonal change that saves a separate cycle.

## Supersedes / Extends

**Extends**: `ADR-0009-reproducible-contributor-entry-point` (mise as canonical entry point). **Closes**: the M2 spec ADDED-7 (lazy MCP import) as a side-effect.

## Verification

Gates touched: `ARCH-BASELINE-001`, `ARCH-DELIVERY-001`, `ARCH-WIRING-001`, `APP-COVERAGE-001`, `ARCH-ACTIVEGRAPH-001`, `ARCH-GRAPH-LEAK-001`, `ARCH-APP-CONCRETE-001`, `DELTA-DET-001`, `GATE-NO-NEW-DRIFT-001`, `PROVIDER-PROVENANCE-001`, `CTX-BUDGET-001`, `SESSION-STALE-001`, `LEARN-NO-AUTO-ACCEPT-001` (all 16 gates are now CI-enforced).

Test files: existing CI tests + `python/tests/test_application_api_coverage.py` (tracked) + `python/tests/test_arc_010_invariant.py` (new).

Evidence: `mise run ci` completes with exit 0; `ci/github-actions/ci.yml` invokes `mise run ci`.

Source traceability: proposal.md sha256 `eb437176358e` · spec.md sha256 `c814be1d` · design.md sha256 `1d9dc45e`.

## Acceptance Criteria

1. `mise.toml[tasks.ci]` updated: `depends = ["lint", "test:python", "test:bats", "verify:architecture"]`. Add `[tasks."verify:architecture"]` block that invokes `arch_conformance.py`.
2. `python/tests/test_application_api_coverage.py` is `git add`'d and registered such that `mise run test:python` invokes it (and emits dual strict/liberal numerators per ADR-0060).
3. Lazy MCP import guard implemented in `delivery/cli/mcp.py`: `from mcp.server import Server` moved inside `register()`; raises `click.ClickException("Install archskillkit[mcp] to use the MCP server")` when `mcp` is not importable.
4. CI fails on (a) any `new_findings` from `arch_conformance.py` against `architecture-baseline.json`, (b) `APP-COVERAGE-001` < 0.9 (per ADR-0060), (c) any new `ARC-002/004/005/010` hit.
5. At apply phase, the 25 non-blocking vault wikilink errors reduce by ≥9 (forward-references become live `[[wikilinks]]` once the 6 ADRs + INC node + capability are mirrored at apply).

## Reversibility

**MEDIUM** — adding `verify:architecture` to `mise run ci` is one-way in practice. Removing it after merges rely on it would silently allow ARC regressions. Mechanical revert is one-line revert in `mise.toml`; semantic revert is significant.

## Deciders

rubentxu

## Date

2026-09-06

## References

- Proposal: `p-f58d41952fdf56c1/v2-5-alignment-adr/propose/proposal.md` (sha256 eb437176358e)
- Spec: `p-f58d41952fdf56c1/v2-5-alignment-adr/specify/spec.md` (sha256 c814be1d)
- Design: `p-f58d41952fdf56c1/v2-5-alignment-adr/design/design.md` (sha256 1d9dc45e)
- Explore report: `p-f58d41952fdf56c1/v2-5-alignment-adr/explore/explore-report.md` (sha256 236ae5cb0962e7b939e154c979abfa4f35a5eccd22f910fdf941c12f96a6f8c4)
