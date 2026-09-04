#!/usr/bin/env python3
"""Deterministic architecture conformance verifier for ArchSkillKit.

Stdlib-only. Findings are stable across runs for the same source tree/contracts.
Baseline comparison is exact: replacing one old violation with another fails.
"""
from __future__ import annotations

import argparse
import ast
import json
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
    findings: list[Finding] = []
    for path in sorted(root.rglob("*.py")):
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


def finding_set(payload: dict) -> set[tuple]:
    return {
        (f["rule_id"], f["path"], int(f["line"]), f["kind"], f["detail"])
        for f in payload.get("findings", [])
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
    report = canonical_payload(findings)

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
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)

    # Existing baseline debt is tolerated; any new exact violation fails.
    return 1 if new or any(f.rule_id.startswith("VERIFIER-") for f in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
