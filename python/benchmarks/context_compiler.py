#!/usr/bin/env python3
"""Persisted, reproducible V2.1 Context Compiler performance evidence.

The harness uses only the Python standard library for timing, memory tracking,
fixture generation and JSON output. It imports ArchSkillKit from the
environment under test, but intentionally requires neither pytest nor a
benchmark framework. An installation command is never run unless both
``--measure-installation`` and an argv-only ``--installation-command-json``
are supplied explicitly.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time
import tracemalloc
from typing import Callable, TypeVar
from uuid import uuid4

import archskillkit
from archskillkit.codeindex import CodeIndex
from archskillkit.context import ContextCompiler
from archskillkit.world import ArchitectureWorld

T = TypeVar("T")


def _positive(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def _argv_array(value: str) -> list[str]:
    """Accept a JSON argv array, never a shell command string."""
    try:
        command = json.loads(value)
    except json.JSONDecodeError as error:
        raise argparse.ArgumentTypeError("must be a JSON argv array") from error
    if not isinstance(command, list) or not command or not all(
            isinstance(part, str) and part for part in command):
        raise argparse.ArgumentTypeError(
            "must be a non-empty JSON array of non-empty strings")
    return command


def _measure(action: Callable[[], T]) -> tuple[T, int, int]:
    """Measure one operation and its isolated tracemalloc peak in bytes."""
    tracemalloc.start()
    try:
        started = time.perf_counter_ns()
        result = action()
        duration_ns = time.perf_counter_ns() - started
        _, peak_bytes = tracemalloc.get_traced_memory()
        return result, duration_ns, peak_bytes
    finally:
        tracemalloc.stop()


def _workload(source_root: Path, file_count: int) -> tuple[str, list[Path]]:
    """Create a deterministic indexed-source corpus without test fixtures."""
    records: list[dict] = []
    paths: list[Path] = []
    for number in range(file_count):
        name = f"service_{number:04d}"
        relative = Path("src") / f"{name}.py"
        path = source_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        text = (
            f"def {name}():\n"
            f"    return {number}\n"
            "\n"
            "# deterministic benchmark source\n"
        )
        path.write_text(text, encoding="utf-8")
        paths.append(path)
        records.append({
            "text": name,
            "ruleId": "python.function",
            "file": str(path),
            "range": {"start": {"line": 0}},
            "lines": text,
            "language": "python",
        })
    return "\n".join(json.dumps(record, sort_keys=True) for record in records), paths


def _broad_source_scan(paths: list[Path], iterations: int) -> dict[str, int]:
    """Agent-only baseline: read every indexed source file per request."""
    reads = 0
    bytes_read = 0
    for _ in range(iterations):
        for path in paths:
            path.read_text(encoding="utf-8")
            reads += 1
            bytes_read += path.stat().st_size
    return {"source_file_reads": reads, "source_bytes_read": bytes_read}


def _package_provenance() -> dict[str, str | None]:
    try:
        version = metadata.version("archskillkit")
    except metadata.PackageNotFoundError:
        version = None
    return {
        "distribution": "archskillkit",
        "version": version,
        "module_file": getattr(archskillkit, "__file__", None),
    }


def _installation_not_measured(reason: str) -> dict:
    return {
        "status": "not_measured",
        "reason": reason,
        "duration_ns": None,
        "peak_bytes": None,
        "result": None,
    }


def _measure_installation(command: list[str] | None, requested: bool) -> dict:
    if not requested:
        return _installation_not_measured("not_requested: --measure-installation was not set")
    if command is None:
        return _installation_not_measured(
            "not_measured: no --installation-command-json argv array was supplied")

    try:
        completed, duration_ns, peak_bytes = _measure(
            lambda: subprocess.run(command, shell=False, capture_output=True, text=True))
    except OSError as error:
        return {
            "status": "error",
            "duration_ns": None,
            "peak_bytes": None,
            "command_argv": command,
            "result": {"error": str(error)},
        }
    return {
        "status": "passed" if completed.returncode == 0 else "failed",
        "duration_ns": duration_ns,
        "peak_bytes": peak_bytes,
        "command_argv": command,
        "result": {
            "return_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        },
    }


def run(file_count: int, iterations: int, installation_command: list[str] | None,
        measure_installation: bool) -> dict:
    """Measure ingestion, query, context compilation and isolated peak memory."""
    with tempfile.TemporaryDirectory(prefix="archskillkit-benchmark-") as temp:
        root = Path(temp)
        source_root = root / "repository"
        data_home = root / "data"
        state_home = root / "state"
        previous_env = {key: os.environ.get(key) for key in
                        ("XDG_DATA_HOME", "XDG_STATE_HOME")}
        os.environ["XDG_DATA_HOME"] = str(data_home)
        os.environ["XDG_STATE_HOME"] = str(state_home)
        world = None
        index = None
        try:
            payload, paths = _workload(source_root, file_count)
            world = ArchitectureWorld(
                project_id="context-compiler-benchmark",
                name="context-compiler-benchmark",
                root=str(source_root),
            ).open()
            world.ensure_project()
            index = CodeIndex(world.workspace / "code.sqlite").open()

            ingest_report, ingest_ns, ingest_peak = _measure(
                lambda: index.ingest_astgrep(
                    payload, scan_run_id="benchmark-1", scan_root=source_root))
            query_results, query_ns, query_peak = _measure(
                lambda: [index.search_symbol("service_0000")
                         for _ in range(iterations)])

            compiler = ContextCompiler(world, index, source_root=source_root)
            packs, compiler_ns, compiler_peak = _measure(
                lambda: [compiler.compile(
                    goal="show the selected service", subject="service_0000")
                    for _ in range(iterations)])
            compiler_metrics = packs[-1].metrics
            compiler_reads = compiler_metrics["source_file_reads"]
            compiler_bytes = compiler_metrics["source_bytes_read"]
            query_result_count = sum(len(result) for result in query_results)
            snippet_count = sum(len(pack.source_snippets) for pack in packs)

            baseline, baseline_ns, baseline_peak = _measure(
                lambda: _broad_source_scan(paths, iterations))
        finally:
            if index is not None:
                index.close()
            if world is not None:
                world.close()
            for key, value in previous_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    meaningful = {
        "query_results": query_result_count > 0,
        "source_snippets": snippet_count > 0,
        "actual_source_reads": compiler_reads > 0,
    }
    is_meaningful = all(meaningful.values())
    reduction = None
    if is_meaningful and baseline["source_file_reads"] > 0:
        reduction = 100 * (baseline["source_file_reads"] - compiler_reads) / baseline["source_file_reads"]
    reasons = [name for name, passed in meaningful.items() if not passed]
    return {
        "schema_version": 2,
        "run": {
            "id": str(uuid4()),
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "platform": platform.platform(),
            "python": sys.version,
            "package": _package_provenance(),
            "invocation_argv": sys.argv,
        },
        "workload": {
            "source_files": file_count,
            "iterations": iterations,
            "target_symbol": "service_0000",
            "source_contents": "generated deterministic Python functions",
        },
        "measurements": {
            "ingest": {"duration_ns": ingest_ns, "peak_bytes": ingest_peak,
                       "files": ingest_report.files, "symbols": ingest_report.symbols},
            "query": {"duration_ns": query_ns, "peak_bytes": query_peak,
                      "operations": iterations, "result_count": query_result_count},
            "context_compiler": {
                "duration_ns": compiler_ns, "peak_bytes": compiler_peak,
                "operations": iterations, "source_snippet_count": snippet_count,
                "source_file_reads": compiler_reads, "source_bytes_read": compiler_bytes,
            },
            "broad_indexed_source_scan": {
                "duration_ns": baseline_ns, "peak_bytes": baseline_peak, **baseline,
            },
            "memory_scope": (
                "peak_bytes is tracemalloc's peak allocated memory for that operation "
                "only; tracing is stopped and restarted before every measured phase."
            ),
            "installation": _measure_installation(installation_command, measure_installation),
        },
        "context_compiler_source_read_kpi": {
            "definition": (
                "Compared with an agent-only baseline that reads every indexed source "
                "file for each request, the Context Compiler reads only index-resolved "
                "snippet source files for the same requests."
            ),
            "meaningful_result_requirements": meaningful,
            "baseline_source_file_reads": baseline["source_file_reads"],
            "compiler_source_file_reads": compiler_reads,
            "reduction_percent": reduction,
            "target_reduction_percent": 50,
            "meets_target": is_meaningful and reduction is not None and reduction >= 50,
            "status": "measured" if is_meaningful else "invalid",
            "invalid_reason": None if is_meaningful else (
                "KPI requires query results, source snippets, and positive actual "
                "source reads; missing: " + ", ".join(reasons)
            ),
        },
    }


def _write_evidence(output: Path, evidence: dict) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    evidence["artifact"] = {"path": str(output), "persistence": "required"}
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--files", type=_positive, default=100,
                        help="number of generated indexed source files (default: 100)")
    parser.add_argument("--iterations", type=_positive, default=10,
                        help="queries and compiler requests to measure (default: 10)")
    parser.add_argument("--output", type=Path, required=True,
                        help="required persisted JSON evidence artifact path")
    parser.add_argument("--measure-installation", action="store_true",
                        help="opt in to executing the supplied installation argv array")
    parser.add_argument("--installation-command-json", type=_argv_array,
                        help="JSON argv array only; never interpreted by a shell")
    args = parser.parse_args()
    if args.installation_command_json and not args.measure_installation:
        parser.error("--installation-command-json requires --measure-installation")
    evidence = run(args.files, args.iterations, args.installation_command_json,
                   args.measure_installation)
    _write_evidence(args.output, evidence)
    print(json.dumps(evidence, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
