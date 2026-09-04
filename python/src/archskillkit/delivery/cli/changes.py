"""`archskillkit changes` — live ArchitectureDelta between main and a proposal fork
(V2.5 M4, ADR-0050).

Compares the live main world against a proposal fork run and emits the
full ArchitectureDelta (elements, relations, unknowns, drift, policy_impacts)
as deterministic JSON. Read-only; same states always yield byte-equivalent
output (DELTA-DET-001).

Usage:
  archskillkit changes --repo . --name my-proposal
  archskillkit changes --repo . --name my-proposal --format markdown
"""

from __future__ import annotations

import argparse
import json
import sys

from archskillkit.application.queries.delta import (
    ArchitectureDelta,
    SnapshotState,
    compute_delta_states,
)

NAME = "changes"
NEEDS_WORLD = True
PROPOSAL_PREFIX = "proposal-"


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        NAME,
        help="live ArchitectureDelta between main world and a proposal fork",
    )
    p.add_argument(
        "--repo",
        required=True,
        help="path to the arch-skillkit repository",
    )
    p.add_argument(
        "--name",
        required=True,
        help="proposal name (the fork is proposal-<name>)",
    )
    p.add_argument(
        "--format",
        choices=["json", "markdown"],
        default="json",
        help="output format (default: json)",
    )
    p.add_argument(
        "--out",
        help="write output to PATH instead of stdout",
    )


def handle(args: argparse.Namespace, world=None) -> int:
    if world is None:
        print("error: --repo is required", file=sys.stderr)
        return 2

    run_id = f"{PROPOSAL_PREFIX}{args.name}"
    if not world.has_run(run_id):
        print(
            f"error: no proposal fork '{run_id}' "
            f"(run: archskillkit proposals create --repo {args.repo} --name {args.name})",
            file=sys.stderr,
        )
        return 1

    try:
        main_state = SnapshotState.from_world(world)
    except RuntimeError as exc:
        print(f"error: failed to capture main world state: {exc}", file=sys.stderr)
        return 1

    try:
        with world:
            fork = world.view(run_id)
            fork_state = SnapshotState.from_world(fork)
    except RuntimeError as exc:
        print(f"error: failed to capture fork state: {exc}", file=sys.stderr)
        return 1

    delta = compute_delta_states(
        main_state,
        fork_state,
        base_snapshot_id=f"main:{world.run_id}",
        head_snapshot_id=f"proposal:{args.name}",
    )

    if args.format == "markdown":
        out = _render_markdown(delta, args.name)
    else:
        out = json.dumps(delta.model_dump(), indent=2) + "\n"

    if args.out:
        from pathlib import Path
        Path(args.out).write_text(out)
    else:
        sys.stdout.write(out)
    return 0


def _render_markdown(delta: ArchitectureDelta, proposal_name: str) -> str:
    lines = [
        f"## ArchitectureDelta — `{proposal_name}`",
        "",
        f"Base: `{delta.base_snapshot}`  |  Head: `{delta.head_snapshot}`",
        "",
    ]

    # Elements
    if delta.elements.added or delta.elements.removed or delta.elements.changed:
        lines.append("### Elements")
        if delta.elements.added:
            lines.append(f"**Added** ({len(delta.elements.added)}): " + ", ".join(f"`{n}`" for n in delta.elements.added))
        if delta.elements.removed:
            lines.append(f"**Removed** ({len(delta.elements.removed)}): " + ", ".join(f"`{n}`" for n in delta.elements.removed))
        if delta.elements.changed:
            lines.append(f"**Changed** ({len(delta.elements.changed)}): " + ", ".join(f"`{n}`" for n in delta.elements.changed))
        lines.append("")

    # Relations
    if delta.relations.added or delta.relations.removed or delta.relations.changed:
        lines.append("### Relations")
        if delta.relations.added:
            lines.append(f"**Added** ({len(delta.relations.added)}):")
            for r in delta.relations.added:
                lines.append(f"  - {r}")
        if delta.relations.removed:
            lines.append(f"**Removed** ({len(delta.relations.removed)}):")
            for r in delta.relations.removed:
                lines.append(f"  - {r}")
        if delta.relations.changed:
            lines.append(f"**Changed** ({len(delta.relations.changed)}):")
            for r in delta.relations.changed:
                lines.append(f"  - {r}")
        lines.append("")

    # Unknowns
    if delta.unknowns:
        u = delta.unknowns
        lines.append(
            f"### Unknowns  "
            f"(base: {u.get('base', 0)} → head: {u.get('head', 0)}  "
            f"Δ {u.get('delta', 0):+d})"
        )
        lines.append("")

    # Drift
    if delta.drift:
        d = delta.drift
        lines.append(
            f"### Drift  "
            f"(base findings: {d.get('findings_base', 0)}  "
            f"→ head findings: {d.get('findings_head', 0)}  "
            f"Δ {d.get('delta', 0):+d})"
        )
        lines.append("")

    # Policy impacts
    if delta.policy_impacts:
        lines.append(f"### Policy Impacts ({len(delta.policy_impacts)})")
        for imp in delta.policy_impacts:
            lines.append(f"- {imp}")
        lines.append("")

    return "\n".join(lines) + "\n"
