"""LikeC4 viewer: managed local server (docs/v2/54 §4 MANAGED_SERVER).

ArchSkillKit starts `likec4 start <workspace>` and registers the PID in
the RuntimeRegistry so the process is visible, stoppable and reaped if
orphaned. Resolution order: PATH first, then the mise install used by
`scripts/oss/view.sh` (same machine layout).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from archskillkit.viewers.contract import (
    ViewerAdapter,
    ViewerCapabilities,
    ViewerDescriptor,
)


def _supports_server(binary: str) -> bool:
    """Capability probe: a managed server needs the `start` command.
    Some installed CLI shims are partial (e.g. export-only) — existence
    alone is not availability."""
    try:
        proc = subprocess.run([binary, "--help"], capture_output=True,
                              text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    return "start" in proc.stdout


def find_likec4_binary() -> str | None:
    """First candidate that actually supports the managed server:
    PATH first, then the mise installs used by scripts/oss/view.sh."""
    candidates = [which for which in [shutil.which("likec4")] if which]
    home = os.environ.get("HOME", "")
    candidates.extend(
        str(p) for p in Path(home or "/nonexistent").glob(
            ".local/share/mise/installs/npm-likec4/*/node_modules/.bin/likec4")
        if p.is_file())
    for candidate in candidates:
        if _supports_server(candidate):
            return candidate
    return None


class LikeC4Viewer(ViewerAdapter):
    """Serves the LikeC4 workspace directory interactively."""

    def descriptor(self) -> ViewerDescriptor:
        return ViewerDescriptor(
            id="likec4-server",
            name="LikeC4 managed server",
            consumes=["likec4"],
            modes=["MANAGED_SERVER", "LOCAL_PROCESS"],
            capabilities=ViewerCapabilities(view=True, edit=False,
                                            round_trip=False),
        )

    def probe(self) -> dict:
        binary = find_likec4_binary()
        return {"available": binary is not None,
                "detail": binary or "likec4 not found in PATH or mise"}

    def launch_argv(self, artifact: Path) -> list[str]:
        binary = find_likec4_binary() or "likec4"
        workspace = artifact if artifact.is_dir() else artifact.parent
        return [binary, "start", str(workspace)]
