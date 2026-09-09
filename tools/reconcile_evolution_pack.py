#!/usr/bin/env python3
"""Pack reconciliation tool for the v2.5 evolution pack.

Validates the consistency between MANIFEST.json, quality-gates.json,
traceability.json, and uat-v2.5-plan.json under the pack directory.

Exit codes:
    0 — reconciliation passed (manifest + README re-rendered if --write)
    1 — drift detected (manifest hash mismatch or README mismatch)
    2 — invalid arguments

Usage:
    python3 tools/reconcile_evolution_pack.py \\
        --pack-dir docs/archive/v2.5-pack/arch-skillkit-v2.5-evolution-pack \\
        --manifest MANIFEST.json \\
        --output-manifest MANIFEST.json.new \\
        --output-readme README.md.new

    python3 tools/reconcile_evolution_pack.py \\
        --pack-dir docs/archive/v2.5-pack/arch-skillkit-v2.5-evolution-pack \\
        --manifest MANIFEST.json
        # dry-run: reads and validates, exits 0 if all hashes match
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import NoReturn


SCHEMA = "arch-skillkit/pack-reconcile-report-v1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _emit_report(findings: list[dict]) -> dict:
    has_mismatch = any(f["kind"].endswith("mismatch") for f in findings)
    exit_class = "ok" if not findings else ("drift" if has_mismatch else "validation")
    return {
        "schema": SCHEMA,
        "findings": findings,
        "exit_class": exit_class,
    }


def _check_manifest_sha(pack_dir: Path, manifest: dict) -> list[dict]:
    findings: list[dict] = []
    for entry in manifest.get("files", []):
        rel = entry["path"]
        declared = entry.get("sha256")
        if declared is None:
            findings.append({"kind": "entry-missing-sha256", "path": rel})
            continue
        actual_path = pack_dir / rel
        if not actual_path.exists():
            findings.append({"kind": "missing-file", "path": rel})
            continue
        actual = _sha256(actual_path)
        if actual != declared:
            findings.append({
                "kind": "manifest-sha-mismatch",
                "path": rel,
                "declared": declared,
                "actual": actual,
            })
    return findings


def _check_gates_formula(pack_dir: Path) -> list[dict]:
    findings: list[dict] = []
    gates_path = pack_dir / "verification" / "quality-gates.json"
    if not gates_path.exists():
        return findings
    gates_doc = _load_json(gates_path)
    for gate in gates_doc.get("gates", []):
        if "formula" not in gate and "formula_ref" not in gate:
            findings.append({"kind": "gate-missing-formula", "gate_id": gate.get("id", "?")})
    return findings


def _check_uats_acceptance_text(pack_dir: Path) -> list[dict]:
    findings: list[dict] = []
    uat_path = pack_dir / "verification" / "uat-v2.5-plan.json"
    if not uat_path.exists():
        return findings
    uat_doc = _load_json(uat_path)
    uat_list = uat_doc.get("uat", []) or uat_doc.get("scenarios", [])
    for uat in uat_list:
        if not uat.get("acceptance_text"):
            findings.append({"kind": "uat-missing-acceptance-text", "uat_id": uat.get("id", "?")})
    return findings


def _check_traceability_consistency(pack_dir: Path) -> list[dict]:
    findings: list[dict] = []
    tr_path = pack_dir / "verification" / "traceability.json"
    gates_path = pack_dir / "verification" / "quality-gates.json"
    uat_path = pack_dir / "verification" / "uat-v2.5-plan.json"
    adr_glob = pack_dir / "docs" / "v2" / "adr" / "ADR-*.md"

    adr_ids: set[str] = set()
    if adr_glob.parent.exists():
        adr_ids = {p.stem.split("-")[0] for p in adr_glob.parent.glob("ADR-*.md") if p.stem}

    gate_ids: set[str] = set()
    if gates_path.exists():
        gate_ids = {g["id"] for g in _load_json(gates_path).get("gates", [])}

    uat_ids: set[str] = set()
    if uat_path.exists():
        uat_ids = {u["id"] for u in _load_json(uat_path).get("uat", []) or []}
        if not uat_ids:
            uat_ids = {u["id"] for u in _load_json(uat_path).get("scenarios", [])}

    if not tr_path.exists():
        return findings
    tr_doc = _load_json(tr_path)
    for link in tr_doc.get("links", []):
        link_id = link.get("id", "?")
        for adr_id in link.get("adrs", []):
            if adr_id not in adr_ids:
                findings.append({"kind": "traceability-adr-missing", "adr": adr_id, "link": link_id})
        for gate_id in link.get("gates", []):
            if gate_id not in gate_ids:
                findings.append({"kind": "traceability-gate-missing", "gate": gate_id, "link": link_id})
        for uat_id in link.get("uats", []):
            if uat_id not in uat_ids:
                findings.append({"kind": "traceability-uat-missing", "uat": uat_id, "link": link_id})
    return findings


def _reconcile(
    pack_dir: Path,
    manifest_path: Path,
    output_manifest: Path | None,
    output_readme: Path | None,
    write: bool,
) -> int:
    """Run all reconciliation checks. Returns exit code."""
    manifest = _load_json(manifest_path)
    findings: list[dict] = []

    findings.extend(_check_manifest_sha(pack_dir, manifest))
    findings.extend(_check_gates_formula(pack_dir))
    findings.extend(_check_uats_acceptance_text(pack_dir))
    findings.extend(_check_traceability_consistency(pack_dir))

    report = _emit_report(findings)
    sys.stdout.write(json.dumps(report, indent=2, sort_keys=True) + "\n")

    has_mismatch = any(f["kind"].endswith("mismatch") for f in findings)

    if has_mismatch:
        return 1

    if findings:
        return 1

    # All clear; re-render if --write
    if write and output_manifest:
        manifest_out = pack_dir / manifest_path.name
        manifest_out.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"Re-rendered MANIFEST: {output_manifest}", file=sys.stderr)

    if write and output_readme:
        readme_path = pack_dir / "README.md"
        if readme_path.exists():
            output_readme.write_bytes(readme_path.read_bytes())
            print(f"Re-rendered README: {output_readme}", file=sys.stderr)

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reconcile the v2.5 evolution pack.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--pack-dir",
        type=Path,
        required=True,
        help="Pack directory containing MANIFEST.json",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        required=True,
        help="Path to MANIFEST.json (absolute or relative to pack-dir)",
    )
    parser.add_argument(
        "--output-manifest",
        type=Path,
        default=None,
        help="Output path for re-rendered MANIFEST.json (requires --write)",
    )
    parser.add_argument(
        "--output-readme",
        type=Path,
        default=None,
        help="Output path for re-rendered README.md (requires --write)",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        default=False,
        help="Re-render MANIFEST.json and README.md to output paths (default: dry-run)",
    )
    args = parser.parse_args(argv)

    # Resolve manifest path
    if args.manifest.is_absolute():
        manifest_path = args.manifest
    else:
        manifest_path = (args.pack_dir / args.manifest).resolve()

    if not manifest_path.exists():
        print(f"ERROR: manifest not found: {manifest_path}", file=sys.stderr)
        return 2

    if args.write:
        if args.output_manifest is None or args.output_readme is None:
            print(
                "ERROR: --write requires both --output-manifest and --output-readme",
                file=sys.stderr,
            )
            return 2

    try:
        return _reconcile(
            args.pack_dir.resolve(),
            manifest_path,
            args.output_manifest,
            args.output_readme,
            args.write,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
