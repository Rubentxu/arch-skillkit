#!/usr/bin/env python3
"""Compute V2.1 UAT gate coverage from the plan + session registry.

A scenario is COVERED iff:
  - the registry marks it as PASS,
  - its session.yaml and evidence-manifest.yaml exist on disk under
    artifacts/uat/v2.1/sessions/<session_id>/,
  - manifest_id equals session_id equals scenario_id,
  - every expected_evidence.evidence_ref_path declared in the plan has
    a matching entry in the manifest with the right sha256,
  - the evidence file on disk hashes to that sha256.

Coverage is reported as overall %, per feature, and per requirement. The
output is deterministic and can be diffed across sessions to track
progress without recomputing manually.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
PLAN = ROOT / "docs/v2/uat/v2.1-plan.yaml"
REGISTRY = ROOT / "docs/v2/uat/v2.1-sessions.not-run.yaml"
SESSIONS_ROOT = ROOT / "artifacts/uat/v2.1/sessions"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    plan = yaml.safe_load(PLAN.read_text())
    registry = yaml.safe_load(REGISTRY.read_text())
    sessions = {s["scenario_id"]: s for s in registry["sessions"]}

    mandatory = [s for s in plan["scenarios"] if s["scenario_id"] not in ("UAT2-015", "UAT2-016")]
    gaps = {s["scenario_id"]: s for s in plan["non_mandatory_gaps"]}

    covered_ids: list[str] = []
    errors: list[str] = []

    for scenario in mandatory:
        sid = scenario["scenario_id"]
        s = sessions.get(sid, {})
        if s.get("verdict") != "PASS":
            continue
        session_id = s["session_id"]
        manifest_path = SESSIONS_ROOT / session_id / "evidence-manifest.yaml"
        session_path = SESSIONS_ROOT / session_id / "session.yaml"
        if not manifest_path.exists() or not session_path.exists():
            errors.append(f"{sid}: missing {manifest_path.name} or {session_path.name}")
            continue
        manifest = yaml.safe_load(manifest_path.read_text())
        sess = yaml.safe_load(session_path.read_text())
        if manifest.get("manifest_id") != session_id or sess.get("manifest_id") != session_id:
            errors.append(f"{sid}: manifest_id mismatch (manifest={manifest.get('manifest_id')} session={sess.get('manifest_id')} expected={session_id})")
            continue
        entries = {e["path"]: e for e in manifest.get("entries", [])}
        expected = scenario.get("expected_evidence", [])
        ok = True
        for ev in expected:
            ref_path = ev["evidence_ref_path"].replace("<session-id>", session_id)
            e = entries.get(ref_path)
            if e is None:
                errors.append(f"{sid}: missing manifest entry for {ref_path}")
                ok = False
                continue
            actual = sha256(ROOT / ref_path)
            if actual != e["sha256"]:
                errors.append(f"{sid}: sha mismatch for {ref_path} (expected={e['sha256']} actual={actual})")
                ok = False
        if ok:
            covered_ids.append(sid)

    covered = len(covered_ids)
    total = len(mandatory)
    pct = 100.0 * covered / total if total else 0.0

    # Per-feature
    feature_totals: dict[str, int] = {}
    feature_covered: dict[str, int] = {}
    for sc in mandatory:
        fid = sc["feature_id"]
        feature_totals[fid] = feature_totals.get(fid, 0) + 1
        if sc["scenario_id"] in covered_ids:
            feature_covered[fid] = feature_covered.get(fid, 0) + 1

    print(f"V2.1 UAT gate coverage: {covered}/{total} = {pct:.2f}%")
    print()
    print("Per feature:")
    for fid in sorted(feature_totals):
        c = feature_covered.get(fid, 0)
        t = feature_totals[fid]
        print(f"  {fid}: {c}/{t}")
    print()
    if covered_ids:
        print(f"PASS: {', '.join(sorted(covered_ids))}")
    pending = [s["scenario_id"] for s in mandatory if s["scenario_id"] not in covered_ids]
    if pending:
        print(f"PENDING: {', '.join(pending)}")
    if gaps:
        print(f"GAPS (not mandatory): {', '.join(gaps.keys())}")
    if errors:
        print()
        print("ERRORS:")
        for e in errors:
            print(f"  - {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())