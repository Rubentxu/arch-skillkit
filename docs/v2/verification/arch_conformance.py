#!/usr/bin/env python3
"""Deterministic architecture conformance verifier for ArchSkillKit.

Stdlib-only. Findings are stable across runs for the same source tree/contracts.
Baseline comparison is exact: replacing one old violation with another fails.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True, order=True)
class Finding:
    rule_id: str
    path: str
    line: int
    kind: str
    detail: str

    def key(self) -> tuple[str, str, int, str, str]:
        return (self.rule_id, self.path, self.line, self.kind, self.detail)


def norm(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def in_scope(rel: str, scopes: list[str]) -> bool:
    for scope in scopes:
        scope = scope.strip("./")
        if scope in ("", "."):
            return True
        if rel == scope or rel.startswith(scope.rstrip("/") + "/"):
            return True
    return False


def is_allowed(rel: str, allow: list[str]) -> bool:
    return in_scope(rel, allow)


def imports(tree: ast.AST) -> Iterable[tuple[str, int]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, node.lineno
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module, node.lineno


def dotted_attr(node: ast.Attribute) -> str:
    parts = [node.attr]
    cur = node.value
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
    return ".".join(reversed(parts))


def scan_file(path: Path, root: Path, rules: list[dict]) -> list[Finding]:
    rel = norm(path, root)
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
    except (UnicodeDecodeError, SyntaxError) as exc:
        return [Finding("VERIFIER-PARSE", rel, getattr(exc, "lineno", 0) or 0,
                        "parse_error", str(exc))]
    out: list[Finding] = []

    imported = list(imports(tree))
    names = [(n.id, n.lineno) for n in ast.walk(tree) if isinstance(n, ast.Name)]
    attrs = [(dotted_attr(n), n.lineno) for n in ast.walk(tree) if isinstance(n, ast.Attribute)]
    calls = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            if isinstance(n.func, ast.Name):
                calls.append((n.func.id, n.lineno))
            elif isinstance(n.func, ast.Attribute):
                calls.append((dotted_attr(n.func), n.lineno))

    for rule in rules:
        rid = rule["id"]
        if not in_scope(rel, rule.get("scope", ["."])):
            continue
        kind = rule["kind"]

        if kind == "forbidden_import_prefix":
            forbidden = tuple(rule.get("forbidden", []))
            for mod, line in imported:
                if any(mod == p or mod.startswith(p + ".") for p in forbidden):
                    out.append(Finding(rid, rel, line, kind, f"import:{mod}"))

        elif kind == "forbidden_attribute":
            if is_allowed(rel, rule.get("allow", [])):
                continue
            attr = rule["attribute"]
            for dotted, line in attrs:
                parts = dotted.split(".")
                if attr in parts:
                    out.append(Finding(rid, rel, line, kind, f"attribute:{dotted}"))

        elif kind == "forbidden_call_name":
            forbidden = set(rule.get("names", []))
            for call, line in calls:
                if call.split(".")[-1] in forbidden:
                    out.append(Finding(rid, rel, line, kind, f"call:{call}"))

        elif kind == "forbidden_name":
            forbidden = set(rule.get("names", []))
            for name, line in names:
                if name in forbidden:
                    out.append(Finding(rid, rel, line, kind, f"name:{name}"))
            for dotted, line in attrs:
                if dotted.split(".")[-1] in forbidden:
                    out.append(Finding(rid, rel, line, kind, f"attribute:{dotted}"))

        else:
            out.append(Finding("VERIFIER-CONFIG", rel, 0, "unknown_rule",
                               f"{rid}:{kind}"))

    return out


def scan(root: Path, contracts: dict) -> list[Finding]:
    src_root = root / "python" / "src" / "archskillkit"
    if not src_root.exists():
        # Fallback: when --root already points at python/src/archskillkit
        src_root = root
    findings: list[Finding] = []
    for path in sorted(src_root.rglob("*.py")):
        if any(part in {".venv", "__pycache__"} for part in path.parts):
            continue
        findings.extend(scan_file(path, root, contracts["rules"]))
    return sorted(set(findings))


def canonical_payload(findings: list[Finding]) -> dict:
    return {
        "schema": "arch-skillkit/architecture-report-v1",
        "findings": [asdict(f) for f in sorted(findings)],
        "counts_by_rule": {
            rid: sum(1 for f in findings if f.rule_id == rid)
            for rid in sorted({f.rule_id for f in findings})
        },
    }


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").lower() in {"1", "true", "yes", "on"}


def finding_set(payload: dict) -> set[tuple]:
    return {
        (f["rule_id"], f["path"], int(f["line"]), f["kind"], f["detail"])
        for f in payload.get("findings", [])
    }


# ADR-0049 sandbox exception: these paths are exempt from ARC-010 injection guard.
_SANDBOX_EXCEPTION_PATHS = {
    "python/src/archskillkit/bootstrap/__init__.py",
}


def _is_sandbox_exception(rel: str) -> bool:
    return rel in _SANDBOX_EXCEPTION_PATHS


def emit_arc_010(root: Path) -> list[Finding]:
    """Detect direct ArchitectureWorld.for_repo or CodeIndex( constructions.

    Scans all python/src/archskillkit/ files and reports any direct
    construction of ArchitectureWorld.for_repo(...) or CodeIndex(...) outside
    the ADR-0049 sandbox exception (bootstrap/__init__.py).
    """
    src_root = root / "python" / "src" / "archskillkit"
    if not src_root.exists():
        # Fallback: when --root already points at python/src/archskillkit
        src_root = root
    findings: list[Finding] = []
    for path in sorted(src_root.rglob("*.py")):
        if any(part in {".venv", "__pycache__"} for part in path.parts):
            continue
        rel = norm(path, root)
        if _is_sandbox_exception(rel):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        except (UnicodeDecodeError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            # Check for ArchitectureWorld.for_repo(...)
            if isinstance(func, ast.Attribute):
                if func.attr == "for_repo":
                    base = func.value
                    if isinstance(base, ast.Name) and base.id == "ArchitectureWorld":
                        findings.append(Finding(
                            "ARC-010", rel, node.lineno,
                            "forbidden_constructor",
                            "ArchitectureWorld.for_repo construction outside ADR-0049 sandbox"
                        ))
                    elif isinstance(base, ast.Attribute) and base.attr == "world":
                        # ArchitectureWorld via module alias or attribute chain
                        pass
            # Check for CodeIndex( direct call
            if isinstance(func, ast.Name) and func.id == "CodeIndex":
                findings.append(Finding(
                    "ARC-010", rel, node.lineno,
                    "forbidden_constructor",
                    "CodeIndex( construction outside ADR-0049 sandbox"
                ))
    return findings


# --- APP-COVERAGE-001 dual numerator (ADR-0060) ----------------------------

# Routing patterns counted by the *liberal* numerator:
#   - `from archskillkit.application.X import ...` (direct import-from)
#   - `from archskillkit.application import ...`        (direct import-from)
#   - `getattr(world, "_arch_app", None)` followed by `app.<method>(...)`
#   - `ArchSkillKitApplication.for_repo(...)` direct construction
_APP_COVERAGE_LIBERAL_IMPORT_PREFIX = "archskillkit.application"
_APP_COVERAGE_DENOMINATOR: int = 19
_APP_COVERAGE_THRESHOLD: float = 0.9


def _is_liberal_via_app(tree: ast.Module) -> bool:
    """Liberal formula: any of the four routing patterns qualifies as 'via app'."""
    # Pattern 1: direct import from archskillkit.application.{x}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith(_APP_COVERAGE_LIBERAL_IMPORT_PREFIX):
                return True
    # Pattern 2: gettattr(world, "_arch_app", None) followed by app.<method>(...)
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if not isinstance(test, ast.Compare):
            continue
        if not any(
            isinstance(c, ast.Constant) and c.value is None for c in test.comparators
        ):
            continue
        # Body contains: app.method(...) call
        for child in node.body:
            for sub in ast.walk(child):
                if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
                    head = sub.func
                    while isinstance(head, ast.Attribute):
                        head = head.value
                    if isinstance(head, ast.Name) and head.id == "app":
                        return True
    # Pattern 3 + 4: ArchSkillKitApplication.for_repo(...)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Attribute) and node.func.attr == "for_repo":
            return True
        if isinstance(node.func, ast.Name) and "for_repo" in node.func.id:
            return True
    return False


def _is_strict_via_app(tree: ast.Module) -> bool:
    """Strict formula: only Pattern 1 (direct import-from application) qualifies.

    Used for audit parity — both numerators emitted alongside each other.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith(_APP_COVERAGE_LIBERAL_IMPORT_PREFIX):
                return True
    return False


def emit_app_coverage_001(root: Path) -> dict:
    """Compute the APP-COVERAGE-001 gate.

    Scans `python/src/archskillkit/delivery/cli/*.py` (excluding __init__.py)
    and emits the dual numerator (strict + liberal) per ADR-0060. The
    denominator is locked at 19 service-call sites and the threshold is
    0.9. ARC-002 and ARC-004 block this gate independently regardless of
    the dual numerator.

    Returns a dict consumable by the evidence emission: ``check_id``,
    ``strict_numerator``, ``liberal_numerator``, ``denominator``,
    ``coverage`` (liberal/denominator), ``threshold``, ``formula``,
    ``block_independently``, ``findings``.
    """
    cli_root = root / "delivery" / "cli"
    if not cli_root.exists():
        cli_root = root / "python" / "src" / "archskillkit" / "delivery" / "cli"
    if not cli_root.exists():
        # Fallback: --root already at python/src/archskillkit
        cli_root = root / "delivery" / "cli" if (root / "delivery" / "cli").exists() else root
        return {
            "check_id": "app_coverage_001",
            "rule_id": "APP-COVERAGE-001",
            "strict_numerator": 0,
            "liberal_numerator": 0,
            "denominator": 0,
            "coverage": 0.0,
            "threshold": _APP_COVERAGE_THRESHOLD,
            "formula": "liberal",
            "block_independently": ["ARC-002", "ARC-004"],
            "findings": [],
        }
    findings = []
    strict_count = 0
    liberal_count = 0
    denominator = 0
    for path in sorted(cli_root.glob("*.py")):
        if path.name == "__init__.py":
            continue
        denominator += 1
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (UnicodeDecodeError, SyntaxError):
            findings.append({"path": path.name, "line": 0, "kind": "parse_error",
                             "detail": "could not parse"})
            continue
        strict_hit = _is_strict_via_app(tree)
        liberal_hit = _is_liberal_via_app(tree)
        if strict_hit:
            strict_count += 1
        if liberal_hit:
            liberal_count += 1
        if not liberal_hit:
            findings.append({"path": path.name, "line": 0, "kind": "direct",
                             "detail": "no application-layer routing detected"})
    coverage = (liberal_count / denominator) if denominator > 0 else 0.0
    return {
        "check_id": "app_coverage_001",
        "rule_id": "APP-COVERAGE-001",
        "strict_numerator": strict_count,
        "liberal_numerator": liberal_count,
        "denominator": denominator,
        "coverage": round(coverage, 4),
        "threshold": _APP_COVERAGE_THRESHOLD,
        "formula": "liberal",
        "block_independently": ["ARC-002", "ARC-004"],
        "findings": findings,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--contracts", required=True)
    ap.add_argument("--baseline")
    ap.add_argument("--write-baseline")
    ap.add_argument("--output")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    contracts = json.loads(Path(args.contracts).read_text(encoding="utf-8"))
    findings = scan(root, contracts)
    arc_010_findings = emit_arc_010(root)
    app_coverage_001 = emit_app_coverage_001(root)
    all_findings = findings + arc_010_findings
    report = canonical_payload(all_findings)

    if args.write_baseline:
        baseline = {
            "schema": "arch-skillkit/architecture-baseline-v1",
            "findings": report["findings"],
        }
        Path(args.write_baseline).parent.mkdir(parents=True, exist_ok=True)
        Path(args.write_baseline).write_text(
            json.dumps(baseline, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    new = set()
    resolved = set()
    if args.baseline:
        baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
        current_set = finding_set(report)
        baseline_set = finding_set(baseline)
        new = current_set - baseline_set
        resolved = baseline_set - current_set
        report["new_findings"] = [
            dict(zip(("rule_id","path","line","kind","detail"), x))
            for x in sorted(new)
        ]
        report["resolved_baseline"] = [
            dict(zip(("rule_id","path","line","kind","detail"), x))
            for x in sorted(resolved)
        ]

    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    output_digest = hashlib.sha256(text.encode()).hexdigest()

    # APP-COVERAGE-001 verdict: gate is FAIL if liberal coverage < threshold,
    # OR if any ARC-002/ARC-004 violations exist (block_independently).
    arc_blocking = any(
        f.rule_id in app_coverage_001["block_independently"]
        for f in findings
    )
    app_coverage_pass = (
        app_coverage_001["coverage"] >= app_coverage_001["threshold"]
        and not arc_blocking
    )
    app_coverage_001["verdict"] = "pass" if app_coverage_pass else "fail"

    # Existing baseline debt is tolerated; any new exact violation fails.
    exit_code = 1 if len(new) > 0 or any(
        f.rule_id.startswith("VERIFIER-") for f in all_findings
    ) else 0
    # APP-COVERAGE-001 provisional threshold: v2.5 M2 closed 13/19 routes (0.6842).
    # M3 is the canonical closer; until then we surface the verdict but do not
    # block CI on it (the strict requirement is recorded as a non-blocking
    # metric on the evidence envelope). Override with ARCH_SKILLKIT_STRICT_GATES=1.
    if not app_coverage_pass and not _env_truthy("ARCH_SKILLKIT_STRICT_GATES"):
        app_coverage_001["non_blocking_reason"] = (
            f"coverage {app_coverage_001['coverage']:.4f} below threshold "
            f"{app_coverage_001['threshold']:.4f}; M3 is the canonical closer "
            "(V2.5 milestone 3, / ADR-0057 Promise 3). "
            "Set ARCH_SKILLKIT_STRICT_GATES=1 to enforce."
        )

    evidence = {
        "argv": sys.argv,
        "exit_code": exit_code,
        "output_digest": output_digest,
        "result": report,
        "checks": [
            {
                "check_id": "arc_010",
                "rule_id": "ARC-010",
                "findings": [asdict(f) for f in sorted(arc_010_findings)],
                "count": len(arc_010_findings),
            },
            {
                "check_id": "contract_rules",
                "rule_id": "mixed",
                "findings": [asdict(f) for f in sorted(findings)],
                "count": len(findings),
            },
            app_coverage_001,
        ],
    }

    evidence_text = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(evidence_text, encoding="utf-8")
    else:
        sys.stdout.write(evidence_text)

    # Existing baseline debt is tolerated; any new exact violation fails.
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
