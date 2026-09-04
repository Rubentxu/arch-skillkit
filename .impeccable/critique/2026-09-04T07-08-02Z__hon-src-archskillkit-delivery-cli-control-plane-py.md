---
target: python/src/archskillkit/delivery/cli/control_plane.py
total_score: 29
p0_count: 0
p1_count: 2
p2_count: 3
timestamp: 2026-09-04T07-08-02Z
slug: hon-src-archskillkit-delivery-cli-control-plane-py
---
# Critique: Architecture Control Plane Shell (V2.4 M5-M6)

## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 3 | Dot indicators work; loading states present; no last-updated timestamp |
| 2 | Match System / Real World | 3 | Clear terms overall; "governance", "candidate", "promote" unexplained |
| 3 | User Control and Freedom | 3 | Panel toggle + close works; no unsaved-changes guard on editor |
| 4 | Consistency and Standards | 4 | Fully consistent token system, ARIA patterns, component vocabulary |
| 5 | Error Prevention | 3 | Input regex validated; admin gate on mutations; no confirm on proposal create |
| 6 | Recognition Rather Than Recall | 2 | No search/filter on evidence; no recent items; 7 panels need labels |
| 7 | Flexibility and Efficiency | 2 | No keyboard shortcuts; favorites strip is the only personalization |
| 8 | Aesthetic and Minimalist Design | 4 | Earned restraint; no decoration; strong hierarchy for a data tool |
| 9 | Error Recovery | 3 | Global error banner + Retry; structured error messages; no undo |
| 10 | Help and Documentation | 2 | Hint covers setup; no inline context on governance/candidates |
| **Total** | | **29/40** | **Good** |

## Anti-Patterns Verdict

**LLM assessment**: No AI slop detectable. The shell reads as a deliberately tool-like, evidence-first instrument. Dark theme is contextually appropriate (engineers inspecting architecture at a terminal). The palette is systematic, not decorative. No gradient text, no hero metrics, no glass cards, no numbered section markers. The one aesthetic risk: the 7-panel layout presents everything at equal visual weight — Coverage (the "fitness profile") looks structurally identical to Findings. This isn't slop, it's a missed hierarchy opportunity.

**Deterministic scan**: CLI detector returned `[]` — zero automated findings. No slop family violations detected. No gradient text, no glassmorphism, no oversized tracked eyebrows.

**Visual overlays**: Browser automation not available in this environment; no live injection performed.

## Overall Impression

The shell is a serious, workmanlike tool that respects its users. It does not try to impress — it tries to inform. The evidence-first mandate is reflected in the architecture: every design decision traces back to a PRODUCT.md principle. The dark theme and system-ui font are the right call for engineers at workstations.

The main structural weakness is **visual hierarchy among panels**. Seven panels arrive at the same weight: Coverage, Evidence, Gaps, Findings, Viewer Hub, draw.io editor, and Arrows viewer. Coverage is the highest-stakes panel — it is the "fitness profile" — but its heading is 0.875rem, same as every other panel. This means a user's eye cannot orient from across the room.

The secondary weakness is **cognitive overhead at first contact**: the token hint is clear, but a user who pastes their token and sees seven panels has no guidance on where to start. The "evidence-first" promise requires telling them where evidence lives first.

## What's Working

1. **The dot-indicator system** — `::before` circles on panel headings with color-coded states (ok/fail/warn/unknown) is an excellent pattern. Immediately scannable, color + shape redundant coding for accessibility.

2. **CSS token discipline** — Every color, spacing, and typography decision traces to a named token. The light-theme fix (separate `@media (prefers-color-scheme: dark)` redeclaration) proved this discipline is applied rigorously.

3. **Error envelope discipline** — Every fetch failure surfaces via global banner with Retry; every non-200 response renders a structured error with the backend `code` field. No silent failures.

4. **The disclosure pattern for evidence** — Evidence items as `<button aria-expanded>` is the correct semantic choice. Progressive disclosure keeps the list scannable while making full provenance available on demand.

## Priority Issues

**[P1] Coverage panel has no visual distinction as the primary status surface**
- **What**: The "Coverage & Unknowns" panel (which PRODUCT.md frames as the "fitness profile") is structurally identical to the other six panels. All h2 headings are 0.875rem.
- **Why it matters**: A user arriving at the page cannot orient without reading. The most important single number (evidence coverage %) is presented at the same visual weight as every other panel. This directly contradicts PRODUCT.md principle 2: "Make unknowns and low coverage visible; false confidence is a product failure."
- **Fix**: Give the Coverage panel's heading a larger font size (e.g. 1.1rem), or add a subtle top-border accent in `--accent` color, or add an `aria-label="Primary status"` to its section. Consider making the Coverage grid the only panel visible by default before user interaction.
- **Suggested command**: `/impeccable layout` — redistribute visual weight across panels; or `/impeccable bolder` — amplify Coverage panel hierarchy.

**[P1] No orientation guidance at first load — seven panels, no sequence**
- **What**: After connecting, seven panels appear simultaneously with no indication of which to read first.
- **Why it matters**: A new user must decode the information architecture by reading every panel. The "evidence-first" promise (PRODUCT.md §4) requires showing evidence provenance FIRST, not leaving it to chance.
- **Fix**: Add a brief `aria-label` on the Evidence panel section describing it as "Architecture evidence with confidence and provenance". Make Evidence panel the one visible by default; collapse others. Alternatively add a one-line orientation sentence in the `#project-strip` area after connect: "You have N evidence items covering M% of the architecture."
- **Suggested command**: `/impeccable clarify` — add orientation copy; `/impeccable layout` — reorder panel default visibility.

**[P2] Governance terms "promote" and "reject" are unexplained inline**
- **What**: The governance action buttons say "Promote" and "Reject" without tooltip or inline context. A new user may not know these are irreversible architecture mutations.
- **Why it matters**: These are high-stakes actions that require the admin gate to even be enabled. A user who sees them enabled (admin server) could click without understanding the consequence.
- **Fix**: Add `title` attribute to both buttons explaining "Promote this proposal into the active architecture" / "Reject and discard this proposal". Or add a `aria-describedby` that points to a visible hint below the buttons.
- **Suggested command**: `/impeccable clarify` — add tooltip + hint copy.

**[P2] Empty states lack CTA — every empty panel shows inert copy**
- **What**: Evidence panel: "No evidence recorded." Gaps panel: "No open knowledge gaps." Each empty state is a single line with no next-step guidance.
- **Why it matters**: PRODUCT.md principle 1: "Put evidence beside the architecture fact." If evidence is absent, the UI should explain how to get it — otherwise the user has to guess.
- **Fix**: Replace generic empty copy with action-oriented copy. Evidence: "Run `archskillkit scan` to populate evidence." Gaps: "Knowledge gaps are populated by the scan process." Governance: "No findings — run a proposal review to surface governance issues."
- **Suggested command**: `/impeccable onboard` — design empty states with activation guidance.

**[P3] The draw.io and Arrows editor panels start expanded when opened**
- **What**: Opening either editor panel renders the iframe immediately at full 420px height. The user must explicitly close it.
- **Why it matters**: The editor is a secondary tool — most users will not open it. Showing it expanded by default adds visual weight to a panel most users will never need.
- **Fix**: Start with the iframe `hidden` and add a "Open editor" trigger inside the collapsed panel body. Or render the panel collapsed by default with a clear "Edit diagram" CTA.
- **Suggested command**: `/impeccable layout` — restructure editor panel with collapsed default.

## Persona Red Flags

**Sam (Accessibility-Dependent)**: The evidence disclosure buttons work well with keyboard and screen reader. However, the 7-panel layout with identical visual weight means Sam must tab through all panels to understand which contains the information they need. No skip-to-content shortcut beyond the banner skip-link.

**Jordan (First-Timer)**: The token hint is now clear (3-step concrete instructions). But after connecting, Jordan sees 7 panels and has no idea where to start. The governance buttons are unlabeled for their consequences. Empty states tell Jordan nothing about what to do next.

**Alex (Power User)**: No keyboard shortcuts. The Viewer Hub favorites (stars) work but require mouse to discover. The governance actions (Promote/Reject) have no keyboard equivalents. Alex cannot efficiently navigate the evidence list without search or filter.

## Minor Observations

- The `h3` for "Available viewers" is hardcoded inside a JS template string — not a semantic `<h3>` in the document structure. Screen readers may not announce it correctly as a heading.
- The draw.io iframe uses `sandbox="allow-scripts"` which is correct (no same-origin needed for external embed), but P1-8 from the UX audit noted this should be validated empirically in a real browser.
- Coverage cards use `1.75rem` for the value — the only large number typography in the interface. This is appropriate for the primary metric but could be confused with decorative "hero metrics" if more numbers grow to the same size.
- The `#project-strip` (project/root/snapshot fields) is rendered from JS on auth — if it fails silently the user sees no project context without understanding why.

## Questions to Consider

1. **"Is the seven-panel layout the right default?"** Evidence-first could mean Evidence + Coverage visible by default, everything else collapsed behind a "More panels" control. Would collapsing the lower-priority panels reduce cognitive load without hiding useful tools?

2. **"Should Coverage be a standalone hero section?"** Doc 66 frames it as the fitness profile — a single prominent display. What if Coverage occupied a top-level banner area, with the 4 metrics as large numbers, before the panel list starts?

3. **"Does 'Promote' need a confirmation dialog?"** It is a governance mutation — but it is also the primary productive action. Is the admin gate sufficient, or does a Promote button need a "Are you sure?" step?

---

**Trend for `hon-src-archskillkit-delivery-cli-control-plane-py` (last 5 runs): First run for this target, no trend yet.**
