#!/usr/bin/env python3
"""Generate the P-03 GraphML artifact for external-viewer validation
(V2.4 M1, docs/v2/uat/v2.4-m1-integration-proofs.md).

The original P-03 artifact (Next.js OSS pilot, 87/55) was lost with its
sandboxed XDG home; this script regenerates an equivalent REAL artifact
(a promoted architecture world with named elements) using the CURRENT
GraphML adapter — including the element `name` data key added by the
P-03 fix (adapter 0.2.0; yEd showed "No Value" without it).

Usage:
  python3 scripts/uat/m1-proof/generate-p03-graphml.py \
      --out artifacts/uat/m1/p03-evidence/p03.graphml

Exit 0 on success.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

_ELEMENTS = [
    # (name, kind, origin, confidence)
    ("payment-svc", "component", "DETECTED", "high"),
    ("orders-api", "component", "DETECTED", "high"),
    ("inventory-svc", "component", "DETECTED", "medium"),
    ("checkout-bounded-context", "bounded_context", "DECLARED", "high"),
    ("billing-bounded-context", "bounded_context", "DECLARED", "high"),
    ("postgres-payments", "datastore", "DETECTED", "high"),
    ("redis-cache", "datastore", "DETECTED", "medium"),
    ("orders-topic", "topic", "INFERRED", "medium"),
    ("payment-gateway", "external_system", "DECLARED", "high"),
    ("public-rest-api", "interface", "DETECTED", "high"),
    ("admin-graphql-api", "interface", "DETECTED", "medium"),
    ("webhook-endpoint", "interface", "INFERRED", "low"),
]

_RELATIONS = [
    # (kind, source, target)
    ("calls", "orders-api", "payment-svc"),
    ("calls", "payment-svc", "inventory-svc"),
    ("publishes", "payment-svc", "orders-topic"),
    ("consumes", "inventory-svc", "orders-topic"),
    ("stores", "payment-svc", "postgres-payments"),
    ("stores", "inventory-svc", "redis-cache"),
    ("calls", "payment-svc", "payment-gateway"),
    ("exposes", "checkout-bounded-context", "public-rest-api"),
    ("exposes", "billing-bounded-context", "admin-graphql-api"),
    ("exposes", "payment-svc", "webhook-endpoint"),
    ("calls", "public-rest-api", "checkout-bounded-context"),
    ("contains", "checkout-bounded-context", "orders-api"),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out", required=True, type=Path, help="output .graphml path")
    args = parser.parse_args()

    from archskillkit.projections.adapters.graphml import GraphMLAdapter
    from archskillkit.projections.writer import project_to_workspace
    from archskillkit.world import ArchitectureWorld

    home = Path(tempfile.mkdtemp(prefix="p03-"))
    os.environ["ARCH_SKILLKIT_HOME"] = str(home)

    repo = home / "demo-repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "main.rs").write_text("fn main() {}\n")
    import subprocess

    def git(*a: str) -> None:
        subprocess.run(["git", "-C", str(repo), *a], check=True,
                       capture_output=True)

    git("init", "-q")
    git("config", "user.email", "p03@example.com")
    git("config", "user.name", "p03")
    git("add", "-A")
    git("commit", "-qm", "init")

    world = ArchitectureWorld.for_repo(str(repo)).open()
    try:
        with world:
            ids: dict[str, str] = {}
            for name, kind, origin, confidence in _ELEMENTS:
                ids[name] = world.add_architecture_element(
                    name, kind, origin=origin, confidence=confidence)
            for kind, source, target in _RELATIONS:
                world.add_architecture_relation(kind, ids[source], ids[target])
        # `with world` closes on exit (transaction scope): reopen for
        # the read-side projection (world.snapshot needs the graph).
        world = world.open()
        result = project_to_workspace(world, GraphMLAdapter())
    finally:
        world.close()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(result["path"], args.out)
    shutil.copyfile(
        Path(result["path"] + ".meta.json"), args.out.with_name(
            args.out.name + ".meta.json"))

    print(f"graphml: {args.out}")
    print(f"metrics: {result['metrics']}")
    print(f"adapter version: {GraphMLAdapter.version}")
    shutil.rmtree(home, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
