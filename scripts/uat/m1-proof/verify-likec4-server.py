#!/usr/bin/env python3
"""P-01 — LikeC4 managed server integration proof (V2.4 M1).

Automates the P-01 gate from docs/v2/uat/v2.4-m1-integration-proofs.md
against REAL artifacts: launch the likec4-server viewer via the
viewer/registry API on the Next.js projection workspace, wait for the
local server to serve HTML, verify the RuntimeRegistry lease, then
stop and verify full teardown.

Stdlib only. Read-only towards any repository.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

from archskillkit.runtime_state.runtime_registry import RuntimeRegistry
from archskillkit.viewers.likec4 import LikeC4Viewer
from archskillkit.viewers.registry import launch, stop

LIKEC4_PORT = 5173


def _server_responds(timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(
                f"http://localhost:{LIKEC4_PORT}/", timeout=timeout) as resp:
            body = resp.read(2048)
            return resp.status == 200 and b"html" in body.lower()
    except OSError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workspace", required=True, type=Path,
        help="directory containing likec4.c4 (served as workspace root)")
    parser.add_argument("--timeout", type=float, default=60.0,
                        help="seconds to wait for the server to come up")
    args = parser.parse_args()

    probe = LikeC4Viewer().probe()
    if not probe["available"]:
        print(json.dumps({"proof": "P-01", "verdict": "SKIP",
                          "reason": probe["detail"]}))
        return 0

    registry = RuntimeRegistry()
    session = launch(LikeC4Viewer(), args.workspace,
                     runtime_registry=registry)
    evidence: dict = {
        "proof": "P-01",
        "viewer": session.viewer_id,
        "pid": session.pid,
        "managed": session.managed,
        "argv": session.argv,
    }
    try:
        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline:
            if _server_responds():
                break
            time.sleep(0.5)
        else:
            evidence.update({"verdict": "FAIL",
                             "reason": f"no HTTP 200 on :{LIKEC4_PORT}"
                                       f" within {args.timeout}s"})
            print(json.dumps(evidence, indent=2))
            return 1

        active = [e.run_id for e in registry.active()]
        evidence.update({
            "server": f"http://localhost:{LIKEC4_PORT}/",
            "http": "200 text/html",
            "runtime_registry_entry": active,
            "verdict": ("PASS" if f"viewer-{session.viewer_id}" in active
                        else "FAIL"),
        })
    finally:
        stop(session, runtime_registry=registry)
        time.sleep(0.3)
        evidence["after_stop"] = {
            "pid_alive": RuntimeRegistry._pid_alive(session.pid),
            "registry": [e.run_id for e in registry.active()],
        }

    if evidence["verdict"] != "PASS":
        print(json.dumps(evidence, indent=2))
        return 1
    if evidence["after_stop"]["pid_alive"]:
        evidence["verdict"] = "FAIL"
        evidence["reason"] = "process survived stop()"
        print(json.dumps(evidence, indent=2))
        return 1
    print(json.dumps(evidence, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
