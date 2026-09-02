"""Markdown renderer for the ArchitectureDelta (V2.4 M3, docs/v2/58).

PR-comment-friendly: one short summary line, then sections per
dimension (added / removed / changed). Empty sections are skipped
so a passing delta renders compactly. Deterministic.
"""

from __future__ import annotations

from archskillkit.application.queries.delta import ArchitectureDelta


def render_delta_markdown(delta: ArchitectureDelta, *,
                          project: str = "",
                          title: str = "Architecture delta") -> str:
    lines: list[str] = [f"# {title}"]
    if project:
        lines.append(f"\nProject: `{project}`")
    summary = _summary(delta)
    lines.append(f"\n{summary}\n")
    _emit_section(lines, "Elements added", delta.elements.added)
    _emit_section(lines, "Elements removed", delta.elements.removed)
    _emit_section(lines, "Elements changed", delta.elements.changed)
    _emit_section(lines, "Relations added", delta.relations.added)
    _emit_section(lines, "Relations removed", delta.relations.removed)
    _emit_section(lines, "Relations changed", delta.relations.changed)
    if delta.unknowns:
        u = delta.unknowns
        sign = "+" if u.get("delta", 0) > 0 else ""
        lines.append("\n## Unknowns")
        lines.append(f"base {u.get('base', 0)} -> head "
                     f"{u.get('head', 0)} ({sign}{u.get('delta', 0)})")
    if delta.drift:
        d = delta.drift
        sign = "+" if d.get("delta", 0) > 0 else ""
        lines.append("\n## Drift findings")
        lines.append(f"base {d.get('findings_base', 0)} -> head "
                     f"{d.get('findings_head', 0)} "
                     f"({sign}{d.get('delta', 0)})")
    return "\n".join(lines) + "\n"


def _summary(delta: ArchitectureDelta) -> str:
    adds = (len(delta.elements.added) + len(delta.relations.added))
    rms = (len(delta.elements.removed) + len(delta.relations.removed))
    chg = (len(delta.elements.changed) + len(delta.relations.changed))
    if not (adds or rms or chg):
        return "No architecture changes detected."
    return (f"{adds} added, {rms} removed, {chg} changed.")


def _emit_section(lines: list[str], title: str, items: list[str]) -> None:
    if not items:
        return
    lines.append(f"\n## {title}")
    for it in items:
        lines.append(f"- `{it}`")
