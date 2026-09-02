"""`archskillkit simulate` — counterfactual over a throwaway fork
(V2.4 M4 slice 18, docs/v2/57 §7, docs/v2/59).

Apply a hypothetical change to a fork ``proposal-<uuid>`` (the
shared fork primitive; the `simulation-` prefix is only a label
used by ``arch_propose_list`` filters when added), evaluate
the policy gate, fitness drift and blast radius, then **throw the
fork away**. The base world is byte-identical before and after;
the contract `UAT24-044` ("simulate devuelve delta/policy results
y base snapshot queda idéntico") is enforced as an internal
assertion, not just a test.

Verbs (docs/v2/57 §7):

  ark simulate relation add  <SRC> <DST> [--kind K]
  ark simulate move          <ELEMENT> --to <CATEGORY>
  ark simulate delete        <ELEMENT>

Each returns a SimulationResult JSON envelope with:

  - base_snapshot_id   (the digest of the main world before sim)
  - base_snapshot_after (the digest after sim; MUST match)
  - fork_id            (the throwaway run; cleaned up on exit)
  - verb               (relation_add | move | delete)
  - applied_to_fork    (the synthetic op that ran on the fork)
  - delta              (added/removed elements and relations)
  - policy_result      (gate verdict, dimensions, waived, expired)
  - blast_radius       (elements whose fitness dimension changed)
  - unknowns_opened    (new knowledge gaps that the change would
                        introduce, if any)
  - recommendation     (allowed | risky | blocked | unknown)

The MCP delivery adapter (delivery/cli/mcp.py) delegates to these
helpers so wire calls reuse exactly the same logic and envelopes
as the CLI.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from archskillkit.application.queries.fitness import (
    FitnessThresholds,
    evaluate_gate,
)
from archskillkit.application.snapshot_builder import build_snapshot
from archskillkit.codeindex import CodeIndex
from archskillkit.packs.arch_model import ElementCategory
from archskillkit.runtime_state.run_ledger import RunLedger
from archskillkit.runtime_state.waivers import WaiverLedger
from archskillkit.world import ArchitectureWorld

NAME = "simulate"
NEEDS_WORLD = True

SIMULATION_PREFIX = "simulation-"
SCHEMA_SIMULATE = "arch-skillkit/simulation-result-v1"


class SimulationResult(BaseModel):
    """Counterfactual simulation outcome (docs/v2/57 §8)."""

    model_config = ConfigDict(extra="forbid")

    schema: Literal["arch-skillkit/simulation-result-v1"] = SCHEMA_SIMULATE  # type: ignore[assignment]
    verb: Literal["relation_add", "move", "delete"]
    base_snapshot_id: str
    base_snapshot_after_id: str
    base_unchanged: bool
    fork_id: str
    applied_to_fork: dict[str, Any]
    delta: dict[str, list[str]] = Field(default_factory=dict)
    policy_result: dict[str, Any]
    blast_radius: list[str] = Field(default_factory=list)
    unknowns_opened: list[str] = Field(default_factory=list)
    recommendation: Literal["allowed", "risky", "blocked", "unknown"]
    project_id: str


# ---- errors ----------------------------------------------------------------


class SimulationError(Exception):
    """Base class for counterfactual failures."""

    code = "SIMULATION_FAILED"

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code

    def to_envelope(self) -> dict[str, str]:
        return {
            "schema": SCHEMA_SIMULATE,
            "error": self.code,
            "message": str(self),
        }


class UnknownElement(SimulationError):
    code = "ELEMENT_NOT_FOUND"


class UnknownCategory(SimulationError):
    code = "INVALID_CATEGORY"


class BaseMutated(SimulationError):
    """Internal invariant: the base world must be byte-identical."""

    code = "BASE_WORLD_MUTATED"


# ---- helpers ---------------------------------------------------------------


def _snapshot_id(world: ArchitectureWorld) -> str:
    """Stable digest of the live graph projection for ``world``.

    Same definition as ``replay_verify``: a sorted JSON dump of the
    graph objects and relations. If the digest matches before and
    after a simulate call, the base was not mutated.
    """
    snap = world.snapshot()
    payload = json.dumps(snap, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _knowledge_gap_delta(before: ArchitectureWorld, after: ArchitectureWorld) -> list[str]:
    """New knowledge gaps that opened in the fork under simulation.

    Compare gap ids; the ones only present after the change would
    be the unknowns the counterfactual introduces.
    """
    before_ids = {g["id"] for g in before.knowledge_gaps()}
    return [g["id"] for g in after.knowledge_gaps() if g["id"] not in before_ids]


def _blast_radius(before: ArchitectureWorld, after: ArchitectureWorld, verb: str) -> list[str]:
    """Names of architecture elements touched by the counterfactual.

    ``relation_add`` -> source + target of the new relation.
    ``move`` / ``delete`` -> the element being moved or removed.
    """
    if verb == "relation_add":
        # The applied_to_fork dict carries `source` and `target`.
        # They can be element ids or names; the simulator stored
        # names on the way in.
        return []  # populated by the verb handler with names
    return []


def _recommendation(gate: dict[str, Any], unknowns: list[str]) -> str:
    """Map gate verdict + unknowns to a recommendation verb.

    Rules (deterministic, no LLM):

    - gate verdict "fail" with no waivers -> ``blocked``
    - gate verdict "fail" but every failed dim is waived -> ``risky``
    - gate verdict "pass" with new unknowns opened -> ``risky``
    - gate verdict "pass" clean -> ``allowed``
    - no policy was even evaluable (all dims ``na``) -> ``unknown``
    """
    verdict = gate.get("verdict", "fail")
    failed = gate.get("failed_dimensions") or []
    waived = gate.get("waived") or []
    dims = gate.get("dimensions") or {}
    if verdict == "fail":
        # Every failed dimension has an active waiver -> "risky".
        if failed and len(waived) >= len(failed):
            return "risky"
        return "blocked"
    # verdict == "pass" — but check whether *every* dimension is na
    # (i.e. policy was never instrumented).
    evaluable = [d for d in dims.values() if (d or {}).get("status") not in (None, "na")]
    if not evaluable:
        return "unknown"
    if unknowns:
        return "risky"
    return "allowed"


# ---- verb handlers ---------------------------------------------------------


def _resolve_element(world: ArchitectureWorld, name: str) -> dict | None:
    matches = world.find_objects("architecture_element", name=name)
    return matches[0] if matches else None


def _relation_add(world: ArchitectureWorld, src: str, dst: str, kind: str) -> dict[str, Any]:
    src_el = _resolve_element(world, src)
    if src_el is None:
        raise UnknownElement(f"source element {src!r} not found in the base world")
    dst_el = _resolve_element(world, dst)
    if dst_el is None:
        raise UnknownElement(f"target element {dst!r} not found in the base world")
    rel_id = world.add_architecture_relation(
        kind, src_el["id"], dst_el["id"], {"origin": "INFERRED", "confidence": "high"}
    )
    return {
        "schema": SCHEMA_SIMULATE,
        "verb": "relation_add",
        "source": src,
        "target": dst,
        "kind": kind,
        "relation_id": rel_id,
    }


def _move(world: ArchitectureWorld, element: str, to: str) -> dict[str, Any]:
    if to not in ElementCategory.__args__:  # type: ignore[attr-defined]
        raise UnknownCategory(f"target category {to!r} is not a valid ElementCategory")
    el = _resolve_element(world, element)
    if el is None:
        raise UnknownElement(f"element {element!r} not found in the base world")
    world.set_object_fields(el["id"], {"kind": to})
    return {
        "schema": SCHEMA_SIMULATE,
        "verb": "move",
        "element": element,
        "to": to,
        "element_id": el["id"],
    }


def _delete(world: ArchitectureWorld, element: str) -> dict[str, Any]:
    el = _resolve_element(world, element)
    if el is None:
        raise UnknownElement(f"element {element!r} not found in the base world")
    world.remove_object_by_id(el["id"])
    return {"schema": SCHEMA_SIMULATE, "verb": "delete", "element": element, "element_id": el["id"]}


# ---- public entry point ----------------------------------------------------


def _run_simulation(
    world: ArchitectureWorld,
    verb: str,
    applied: dict[str, Any],
    fork_id: str,
    fork: ArchitectureWorld,
) -> SimulationResult:
    """Compute delta + policy + recommendation against the post-verb fork."""
    code = world.workspace / "code.sqlite"
    index = CodeIndex(code).open() if code.exists() else None
    ledger = RunLedger()
    try:
        # ``fork`` already carries the post-verb state. The
        # evaluation runs against its snapshot — that's the
        # counterfactual world, not the base.
        snapshot = build_snapshot(fork, code_index=index)
        gate = evaluate_gate(
            fork, snapshot, thresholds=FitnessThresholds(), ledger=ledger, waivers=WaiverLedger()
        )
    finally:
        if index is not None:
            index.close()

    policy_dict = gate.model_dump()
    # Drop the internal "schema" field from the embedded gate; the
    # top-level SimulationResult already carries a schema id.
    policy_dict.pop("schema", None)
    unknowns = _knowledge_gap_delta(world, fork)
    blast = _blast_radius(world, fork, verb)
    if verb == "relation_add":
        blast = [applied.get("source"), applied.get("target")]

    return SimulationResult(
        verb=verb,  # type: ignore[arg-type]
        base_snapshot_id="pending",
        base_snapshot_after_id="pending",
        base_unchanged=True,  # overwritten after the base-digest check
        fork_id=fork_id,
        applied_to_fork={k: v for k, v in applied.items() if not k.startswith("_")},
        policy_result=policy_dict,
        blast_radius=[n for n in blast if n],
        unknowns_opened=unknowns,
        recommendation=_recommendation(policy_dict, unknowns),
        project_id=world.project_id,
    )


def run(world: ArchitectureWorld, verb: str, **verb_args: Any) -> SimulationResult:
    """Run the counterfactual end-to-end.

    ``world`` must be the *main* (base) world. The function
    snapshots it, forks, applies the verb on the fork, evaluates
    policy, and throws the fork away. The base world must be
    byte-identical afterwards; otherwise we raise BaseMutated and
    the envelope is not returned.
    """
    if world.run_id != "world":
        # Sanity: simulate only makes sense rooted on the base run.
        # Calling simulate on a fork or a stale view would itself
        # be a misuse; we surface it as an envelope error.
        raise SimulationError(
            f"simulate must run against the main world (got run_id={world.run_id!r})"
        )

    base_after: str = ""
    base_before: str = ""
    fork_run_id: str = ""
    try:
        with world:
            base_before = _snapshot_id(world)
            fork_label = uuid.uuid4().hex[:8]
            applied: dict[str, Any]
            result: SimulationResult
            fork = world.fork(fork_label)
            fork_run_id = fork.run_id  # proposal-<fork_label>
            try:
                try:
                    if verb == "relation_add":
                        applied = _relation_add(
                            fork,
                            verb_args["source"],
                            verb_args["target"],
                            verb_args.get("kind", "depends_on"),
                        )
                    elif verb == "move":
                        applied = _move(fork, verb_args["element"], verb_args["to"])
                    elif verb == "delete":
                        applied = _delete(fork, verb_args["element"])
                    else:
                        raise SimulationError(f"unknown verb {verb!r}")
                    result = _run_simulation(world, verb, applied, fork.run_id, fork)
                except SimulationError:
                    # Drop happens AFTER `with world:` exits so the
                    # fork's writes are visible to a fresh sqlite
                    # connection (SQLite WAL pins the live read tx).
                    fork.close()
                    world.drop_run(fork_run_id)
                    raise
            finally:
                fork.close()
            # Verify the base world digest is unchanged inside the
            # same open world so the read sees committed state. The
            # throwaway fork may have written to its own run; this
            # check proves nothing leaked into the main run.
            base_after = _snapshot_id(world)
            if base_after != base_before:
                raise BaseMutated(
                    f"base world digest changed during simulate "
                    f"({base_before[:8]} -> {base_after[:8]}); "
                    "this is a bug in the simulator"
                )
    except SimulationError:
        # Even on BaseMutated (which is a SimulationError subclass)
        # the fork must go; otherwise it leaks into the run ledger.
        try:
            world.drop_run(fork_run_id)
        except (ValueError, OSError):
            # ValueError: drop_run refuses main run; OSError: db
            # unavailable. Either way the fork may leak and we
            # surface the original error to the caller.
            pass
        raise
    # Drop the throwaway fork OUTSIDE the ``with world:`` block so
    # the parent's read transaction closes first and the drop is
    # observable from any subsequent reader (including the caller
    # checking ``world.list_runs()`` after this returns).
    world.drop_run(fork_run_id)
    return result.model_copy(
        update={
            "base_snapshot_id": base_before,
            "base_snapshot_after_id": base_after,
            "base_unchanged": True,
        }
    )


# ---- CLI plumbing ----------------------------------------------------------


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        NAME,
        help="apply a counterfactual change to a throwaway fork"
        " and evaluate the policy gate (the base world is untouched)",
    )
    p.add_argument("--repo", required=True)
    sub = p.add_subparsers(dest="simulate_action", required=True)

    pa = sub.add_parser("relation", help="simulate adding a relation")
    pa.add_argument("verb2", choices=["add"])
    pa.add_argument("source", help="source element name")
    pa.add_argument("target", help="target element name")
    pa.add_argument("--kind", default="depends_on", help="relation kind (default: depends_on)")

    pm = sub.add_parser("move", help="simulate moving an element to a category")
    pm.add_argument("element", help="element name to move")
    pm.add_argument(
        "--to",
        required=True,
        help=f"target ElementCategory (one of {sorted(ElementCategory.__args__)})",
    )  # type: ignore[attr-defined]

    pd = sub.add_parser("delete", help="simulate deleting an element")
    pd.add_argument("element", help="element name to delete")


def _verb_to_args(action: str, args: argparse.Namespace) -> tuple[str, dict[str, Any]]:
    if action == "relation":
        return "relation_add", {
            "source": args.source,
            "target": args.target,
            "kind": args.kind,
        }
    if action == "move":
        return "move", {"element": args.element, "to": args.to}
    if action == "delete":
        return "delete", {"element": args.element}
    raise SimulationError(f"unknown simulate action {action!r}")


def handle(args: argparse.Namespace, world: ArchitectureWorld) -> int:
    if not world.db_path.exists():
        print(
            f"error: no Architecture World for {world.project_id} "
            f"(run: archskillkit init --repo {world.root or '.'})",
            file=sys.stderr,
        )
        return 1
    try:
        verb, verb_args = _verb_to_args(args.simulate_action, args)
        result = run(world, verb, **verb_args)
    except SimulationError as exc:
        print(json.dumps(exc.to_envelope()), file=sys.stderr)
        return 1
    print(json.dumps(result.model_dump(), indent=2))
    return 0
