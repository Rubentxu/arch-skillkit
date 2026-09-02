"""Minimal agent-facing facade: `python -m archskillkit <command> --repo PATH`.

Read-only towards the analyzed repository: the only git invocations are
rev-parse / config --get / remote. Exit codes: 0 ok, 1 world/usage error
at runtime, 2 argument or precondition failure. `setup` and `doctor` are
host-level commands (docs/v2/24): they never need a repository, never touch
git, and doctor never uses the network.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from archskillkit.codeindex import CodeIndex, IngestError
from archskillkit.context import Budget, ContextCompiler
from archskillkit.delivery.cli import COMMANDS
from archskillkit.ids import RepoNotFound
from archskillkit.packs.arch_core import ObservationData
from archskillkit.projections.adapters.arrows import ArrowsAdapter
from archskillkit.projections.adapters.drawio import DrawioAdapter
from archskillkit.projections.adapters.graphml import GraphMLAdapter
from archskillkit.projections.adapters.jsoncanvas import JSONCanvasAdapter
from archskillkit.projections.adapters.likec4 import LikeC4Adapter
from archskillkit.projections.writer import ProjectionError, project_to_workspace
from archskillkit.promotion import detect_generation_drift, discover, review
from archskillkit.proposals import (
    PromotionError,
    promote,
    structural_diff,
)
from archskillkit.runtime import SetupError, load_manifest_for_setup, run_doctor, run_setup
from archskillkit.runtime_manifest import ManifestError
from archskillkit.world import ArchitectureWorld


def main(argv: list[str] | None = None) -> int:
    from archskillkit import __version__

    parser = argparse.ArgumentParser(
        prog="archskillkit",
        description="ArchSkillKit V2 Architecture World facade.",
    )
    parser.add_argument("--version", action="version",
                        version=f"archskillkit {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    for name in ("init", "state", "replay-verify"):
        p = sub.add_parser(name)
        p.add_argument("--repo", required=True)

    p_obs = sub.add_parser("record-observation")
    p_obs.add_argument("--repo", required=True)
    p_obs.add_argument("--payload", required=True,
                       help="JSON file following design/schemas/observation.yaml")

    p_ingest = sub.add_parser("ingest-code",
                              help="ingest scanner payloads into code.sqlite")
    p_ingest.add_argument("--repo", required=True)
    p_ingest.add_argument("--astgrep", help="ast-grep --json=stream NDJSON file")
    p_ingest.add_argument("--semgrep", help="semgrep --json file")
    p_ingest.add_argument("--run-id", required=True)
    p_ingest.add_argument("--scan-root", help="root used to relativize paths"
                          " (default: the repository root)")

    p_stats = sub.add_parser("index-stats", help="code.sqlite summary as JSON")
    p_stats.add_argument("--repo", required=True)

    p_search = sub.add_parser("search-code", help="search symbols (FTS prefix)")
    p_search.add_argument("--repo", required=True)
    p_search.add_argument("query")

    p_discover = sub.add_parser(
        "discover", help="full promotion pipeline: scan run → architecture")
    p_discover.add_argument("--repo", required=True)
    p_discover.add_argument("--run-id", required=True)

    p_review = sub.add_parser("review",
                              help="deterministic review of the world")
    p_review.add_argument("--repo", required=True)

    p_ctx = sub.add_parser("context",
                           help="compile a budgeted ContextPack (Phase D)")
    p_ctx.add_argument("--repo", required=True)
    p_ctx.add_argument("--goal", required=True)
    p_ctx.add_argument("--subject", default=None)
    p_ctx.add_argument("--max-nodes", type=int, default=None)
    p_ctx.add_argument("--max-edges", type=int, default=None)
    p_ctx.add_argument("--max-lines", type=int, default=None)

    p_proj = sub.add_parser("project",
                            help="project the world to LikeC4/Arrows artifacts")
    p_proj.add_argument("--repo", required=True)
    p_proj.add_argument(
        "--format",
        choices=["likec4", "arrows", "graphml", "jsoncanvas",
                 "drawio", "all", "both"],
        default="both")
    p_proj.add_argument("--force", action="store_true",
                        help="overwrite a manually modified projection")

    p_drift = sub.add_parser("drift",
                             help="deterministic drift + stale model detection")
    p_drift.add_argument("--repo", required=True)

    p_fork = sub.add_parser("fork",
                            help="branch the world into a proposal run")
    p_fork.add_argument("--repo", required=True)
    p_fork.add_argument("--name", required=True)

    p_diff = sub.add_parser("diff",
                            help="structural diff of a proposal vs the world")
    p_diff.add_argument("--repo", required=True)
    p_diff.add_argument("--name", required=True)

    p_promote = sub.add_parser("promote",
                               help="apply an approved proposal to the world")
    p_promote.add_argument("--repo", required=True)
    p_promote.add_argument("--name", required=True)
    p_promote.add_argument("--approved-by", required=True)

    p_reject = sub.add_parser("reject-proposal",
                              help="reject a proposal, keeping the scenario")
    p_reject.add_argument("--repo", required=True)
    p_reject.add_argument("--name", required=True)
    p_reject.add_argument("--actor", required=True)

    p_setup = sub.add_parser(
        "setup", help="fetch, verify and atomically install the third-party"
        " runtime (host-level; no repository involved)")
    p_setup.add_argument("--manifest",
                         help="path or URL of the runtime manifest (default:"
                         " stored copy, then the release manifest)")
    p_setup.add_argument("--prefetch", action="store_true",
                         help="fill the digest cache and stop; no activation")
    p_setup.add_argument("--offline", action="store_true",
                         help="never open the network; fail if something is"
                         " missing")

    p_doctor = sub.add_parser(
        "doctor", help="read-only installation diagnosis as JSON (never"
        " downloads, never repairs)")
    p_doctor.add_argument("--manifest",
                          help="path or URL of the runtime manifest to"
                          " diagnose against (default: stored copies)")

    # V2.4 delivery-adapter commands (docs/v2/67 slice 4): each module
    # owns its parser and handler through the application layer.
    for module in COMMANDS:
        module.register(sub)

    args = parser.parse_args(argv)

    if args.command == "setup":
        return _cmd_setup(args)
    if args.command == "doctor":
        return _cmd_doctor(args)

    try:
        world = ArchitectureWorld.for_repo(args.repo)
    except RepoNotFound as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print("error: HOST_TOOL_MISSING git is required for repository"
              f" analysis: {exc}", file=sys.stderr)
        return 2

    if args.command == "init":
        return _cmd_init(world)
    if args.command == "state":
        return _cmd_state(world)
    if args.command == "replay-verify":
        return _cmd_replay_verify(world)
    if args.command == "record-observation":
        return _cmd_record_observation(world, Path(args.payload))
    if args.command == "ingest-code":
        return _cmd_ingest_code(world, args)
    if args.command == "index-stats":
        return _cmd_index_stats(world)
    if args.command == "search-code":
        return _cmd_search_code(world, args.query)
    if args.command == "discover":
        return _cmd_discover(world, args.run_id)
    if args.command == "review":
        return _cmd_review(world)
    if args.command == "context":
        return _cmd_context(world, args)
    if args.command == "project":
        return _cmd_project(world, args)
    if args.command == "drift":
        return _cmd_drift(world)
    if args.command == "fork":
        return _cmd_fork(world, args.name)
    if args.command == "diff":
        return _cmd_diff(world, args.name)
    if args.command == "promote":
        return _cmd_promote(world, args.name, args.approved_by)
    if args.command == "reject-proposal":
        return _cmd_reject(world, args.name, args.actor)
    for module in COMMANDS:
        if args.command == module.NAME:
            return module.handle(args, world)
    parser.error(f"unknown command: {args.command}")
    return 2


def _cmd_setup(args: argparse.Namespace) -> int:
    from archskillkit.runtime import Paths

    paths = Paths.from_env()
    try:
        manifest, _source = load_manifest_for_setup(
            paths, args.manifest, offline=args.offline)
        receipt = run_setup(paths, manifest, offline=args.offline,
                            prefetch=args.prefetch)
    except (SetupError, ManifestError) as exc:
        payload = exc.as_dict() if isinstance(exc, SetupError) else {
            "code": "RUNTIME_INCOMPATIBLE", "message": str(exc),
            "remedy": "check the manifest or pass --manifest explicitly"}
        print(json.dumps(payload))
        print(f"error: {payload['message']}", file=sys.stderr)
        return 2
    print(json.dumps(receipt, indent=2))
    return 0


def _cmd_doctor(args: argparse.Namespace) -> int:
    from archskillkit.runtime import Paths, read_manifest_source

    paths = Paths.from_env()
    manifest = None
    if args.manifest:
        try:
            manifest = read_manifest_source(args.manifest)
        except (ManifestError, OSError) as exc:
            print(f"error: unreadable manifest: {exc}", file=sys.stderr)
            return 2
    diagnosis, exit_code = run_doctor(paths, manifest)
    print(json.dumps(diagnosis, indent=2))
    return exit_code


def _cmd_init(world: ArchitectureWorld) -> int:
    world.open()
    try:
        world.ensure_project()
    finally:
        world.close()
    print(json.dumps({
        "project_id": world.project_id,
        "name": world.project_name,
        "workspace": str(world.workspace),
        "activegraph_db": str(world.db_path),
    }))
    return 0


def _require_world(world: ArchitectureWorld) -> str | None:
    if not world.db_path.exists():
        print(
            f"error: no Architecture World for {world.project_id} "
            f"(run: archskillkit init --repo {world.root or '.'})",
            file=sys.stderr,
        )
        return None
    return str(world.db_path)


def _cmd_state(world: ArchitectureWorld) -> int:
    if _require_world(world) is None:
        return 1
    with world:
        print(json.dumps(world.snapshot(), indent=2))
    return 0


def _cmd_replay_verify(world: ArchitectureWorld) -> int:
    if _require_world(world) is None:
        return 1
    with world:
        report = world.replay_verify()
    if report.ok:
        print(f"replay OK: {report.objects} objects, {report.relations} relations, "
              f"{report.events} events ({report.detail})")
        return 0
    print(f"replay FAILED: {report.detail}", file=sys.stderr)
    return 1


def _cmd_record_observation(world: ArchitectureWorld, payload: Path) -> int:
    try:
        observation = ObservationData.model_validate_json(payload.read_text())
    except (ValidationError, OSError) as exc:
        print(f"error: invalid observation payload: {exc}", file=sys.stderr)
        return 2
    with world:
        obs_id = world.record_observation(observation)
    print(obs_id)
    return 0


def _cmd_ingest_code(world: ArchitectureWorld, args: argparse.Namespace) -> int:
    if not args.astgrep and not args.semgrep:
        print("error: provide --astgrep and/or --semgrep payloads",
              file=sys.stderr)
        return 2
    payloads: list[tuple[str, Path]] = []
    if args.astgrep:
        payloads.append(("astgrep", Path(args.astgrep)))
    if args.semgrep:
        payloads.append(("semgrep", Path(args.semgrep)))
    for kind, path in payloads:
        if not path.is_file():
            print(f"error: {kind} payload not found: {path}", file=sys.stderr)
            return 2

    scan_root = args.scan_root or world.root
    totals = {"files": 0, "symbols": 0, "edges": 0, "warnings": []}
    with CodeIndex(world.workspace / "code.sqlite") as index:
        try:
            for kind, path in payloads:
                report = (
                    index.ingest_astgrep(path.read_text(), args.run_id, scan_root)
                    if kind == "astgrep"
                    else index.ingest_semgrep(path.read_text(), args.run_id, scan_root)
                )
                totals["files"] += report.files
                totals["symbols"] += report.symbols
                totals["edges"] += report.edges
                totals["warnings"].extend(report.warnings)
        except (IngestError, OSError) as exc:
            print(f"error: ingest failed: {exc}", file=sys.stderr)
            return 1
    print(json.dumps(totals))
    return 0


def _cmd_index_stats(world: ArchitectureWorld) -> int:
    db = world.workspace / "code.sqlite"
    if not db.exists():
        print(f"error: no code.sqlite for {world.project_id} "
              f"(run: archskillkit ingest-code --repo {world.root or '.'})",
              file=sys.stderr)
        return 1
    with CodeIndex(db) as index:
        print(json.dumps(index.stats(), indent=2))
    return 0


def _cmd_search_code(world: ArchitectureWorld, query: str) -> int:
    db = world.workspace / "code.sqlite"
    if not db.exists():
        print(f"error: no code.sqlite for {world.project_id} "
              f"(run: archskillkit ingest-code --repo {world.root or '.'})",
              file=sys.stderr)
        return 1
    with CodeIndex(db) as index:
        print(json.dumps(index.search_symbol(query), indent=2))
    return 0


def _require_code_index(world: ArchitectureWorld) -> CodeIndex | None:
    db = world.workspace / "code.sqlite"
    if not db.exists():
        print(f"error: no code.sqlite for {world.project_id} "
              f"(run: archskillkit ingest-code --repo {world.root or '.'})",
              file=sys.stderr)
        return None
    return CodeIndex(db).open()


def _cmd_discover(world: ArchitectureWorld, run_id: str) -> int:
    index = _require_code_index(world)
    if index is None:
        return 1
    try:
        with world:
            report = discover(world, index, run_id)
    finally:
        index.close()
    print(json.dumps(report.as_dict(), indent=2))
    return 0


def _cmd_review(world: ArchitectureWorld) -> int:
    with world:
        result = review(world)
    print(json.dumps(result, indent=2))
    return 0


def _cmd_context(world: ArchitectureWorld, args: argparse.Namespace) -> int:
    db = world.workspace / "code.sqlite"
    if not db.exists():
        print(f"error: no code.sqlite for {world.project_id} "
              f"(run: archskillkit discover --repo {world.root or '.'})",
              file=sys.stderr)
        return 1
    if not world.db_path.exists():
        print(f"error: no Architecture World for {world.project_id} "
              f"(run: archskillkit discover --repo {world.root or '.'})",
              file=sys.stderr)
        return 1
    budget = Budget(
        max_nodes=args.max_nodes or 50,
        max_edges=args.max_edges or 100,
        max_source_lines=args.max_lines or 200)
    index = CodeIndex(db).open()
    try:
        with world:
            pack = ContextCompiler(world, index).compile(
                goal=args.goal, subject=args.subject, budget=budget)
    finally:
        index.close()
    print(pack.model_dump_json())
    return 0


def _cmd_project(world: ArchitectureWorld, args: argparse.Namespace) -> int:
    if not world.db_path.exists():
        print(f"error: no Architecture World for {world.project_id} "
              f"(run: archskillkit discover --repo {world.root or '.'})",
              file=sys.stderr)
        return 1
    adapters = {
        "likec4": LikeC4Adapter(),
        "arrows": ArrowsAdapter(),
        "graphml": GraphMLAdapter(),
        "jsoncanvas": JSONCanvasAdapter(),
        "drawio": DrawioAdapter(),
    }
    if args.format == "all":
        targets = list(adapters)
    elif args.format == "both":
        # "both" = the two canonical projections; graphml/jsoncanvas are
        # opt-in formats (F10).
        targets = ["likec4", "arrows"]
    else:
        targets = [args.format]
    results = []
    with world:
        for fmt in targets:
            try:
                results.append(project_to_workspace(
                    world, adapters[fmt], force=args.force))
            except ProjectionError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 1
    print(json.dumps({"projections": results}, indent=2))
    return 0


def _cmd_drift(world: ArchitectureWorld) -> int:
    if not world.db_path.exists():
        print(f"error: no Architecture World for {world.project_id} "
              f"(run: archskillkit discover --repo {world.root or '.'})",
              file=sys.stderr)
        return 1
    with world:
        drift = world.detect_drift()
        db = world.workspace / "code.sqlite"
        stale = {"findings": [], "persisted": 0}
        generation = {"generation": None, "findings": [], "persisted": 0}
        if db.exists():
            index = CodeIndex(db).open()
            try:
                stale = world.detect_stale_model(index)
                generation = detect_generation_drift(world, index)
            finally:
                index.close()
    print(json.dumps({
        "drift": {"findings": drift["findings"], "persisted": drift["persisted"]},
        "stale_model": {"findings": stale["findings"],
                        "persisted": stale["persisted"]},
        "generation_drift": generation,
    }, indent=2))
    return 0


def _require_main_world(world: ArchitectureWorld) -> int | None:
    if not world.db_path.exists():
        print(f"error: no Architecture World for {world.project_id} "
              f"(run: archskillkit discover --repo {world.root or '.'})",
              file=sys.stderr)
        return 1
    return None


def _cmd_fork(world: ArchitectureWorld, name: str) -> int:
    if _require_main_world(world):
        return 1
    with world:
        fork = world.fork(name)
    print(json.dumps({"run_id": fork.run_id, "name": name}))
    return 0


def _cmd_diff(world: ArchitectureWorld, name: str) -> int:
    if _require_main_world(world):
        return 1
    fork_run = f"proposal-{name}"
    if not world.has_run(fork_run):
        print(f"error: no fork run '{fork_run}' (run: archskillkit fork "
              f"--repo {world.root or '.'} --name {name})", file=sys.stderr)
        return 1
    with world:
        fork = world.view(fork_run)
        diff = structural_diff(world, fork)
    result = {k: v for k, v in vars(diff).items()}
    result["is_empty"] = diff.is_empty()
    print(json.dumps(result, indent=2))
    return 0


def _cmd_promote(world: ArchitectureWorld, name: str, approved_by: str) -> int:
    if _require_main_world(world):
        return 1
    fork_run = f"proposal-{name}"
    if not world.has_run(fork_run):
        print(f"error: no fork run '{fork_run}' (run: archskillkit fork "
              f"--repo {world.root or '.'} --name {name})", file=sys.stderr)
        return 1
    with world:
        fork = world.view(fork_run)
        fork.record_proposal(name)
        try:
            fork.approve_proposal(name, actor=approved_by)
            summary = promote(world, fork)
        except PromotionError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
    print(json.dumps(summary, indent=2))
    return 0


def _cmd_reject(world: ArchitectureWorld, name: str, actor: str) -> int:
    if _require_main_world(world):
        return 1
    fork_run = f"proposal-{name}"
    if not world.has_run(fork_run):
        print(f"error: no fork run '{fork_run}'", file=sys.stderr)
        return 1
    with world:
        fork = world.view(fork_run)
        fork.record_proposal(name)
        try:
            fork.reject_proposal(name, actor=actor)
        except PromotionError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
    print(json.dumps({"name": name, "status": "rejected"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
