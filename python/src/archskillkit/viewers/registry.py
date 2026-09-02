"""ViewerRegistry and launch lifecycle (docs/v2/54 §6).

`ark viewers` and `ark doctor` consume this registry. Launch runs the
argv built by the adapter; MANAGED_SERVER processes are registered in
the RuntimeRegistry so they are stoppable and reaped when orphaned —
runtime state lives outside the ArchitectureWorld (ADR-0033).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from archskillkit.runtime_state.runtime_registry import RuntimeEntry, RuntimeRegistry
from archskillkit.viewers.contract import (
    ViewerAdapter,
    ViewerUnavailable,
)
from archskillkit.viewers.drawio import DrawioDesktopViewer
from archskillkit.viewers.likec4 import LikeC4Viewer
from archskillkit.viewers.system_default import SystemDefaultViewer


@dataclass(frozen=True)
class ViewerSession:
    viewer_id: str
    pid: int
    argv: list[str]
    managed: bool
    process: subprocess.Popen | None = None


class ViewerRegistry:
    def __init__(self, adapters: list[ViewerAdapter] | None = None):
        self._adapters = list(adapters) if adapters is not None else [
            LikeC4Viewer(),
            DrawioDesktopViewer(),
            SystemDefaultViewer(),
        ]

    def adapters(self) -> list[ViewerAdapter]:
        return list(self._adapters)

    def status(self) -> list[dict]:
        """One row per viewer: descriptor + live probe result."""
        rows = []
        for adapter in self._adapters:
            descriptor = adapter.descriptor()
            rows.append({**descriptor.model_dump(),
                         "probe": adapter.probe()})
        return rows

    def find(self, viewer_id: str) -> ViewerAdapter:
        for adapter in self._adapters:
            if adapter.descriptor().id == viewer_id:
                return adapter
        raise ViewerUnavailable(f"unknown viewer: {viewer_id}")

    def route(self, fmt: str, explicit: str | None = None,
              require_available: bool = True) -> ViewerAdapter:
        """First available viewer that consumes `fmt`; an explicit id
        wins and must consume the format. Preference order is the
        adapter registration order, system-default last."""
        if explicit:
            adapter = self.find(explicit)
            if fmt not in adapter.descriptor().consumes:
                raise ViewerUnavailable(
                    f"viewer {explicit} does not consume {fmt}")
            probe = adapter.probe()
            if require_available and not probe.get("available"):
                raise ViewerUnavailable(
                    f"viewer {explicit} unavailable: {probe.get('detail')}")
            return adapter
        system_default: ViewerAdapter | None = None
        for adapter in self._adapters:
            if fmt not in adapter.descriptor().consumes:
                continue
            if adapter.descriptor().id == "system-default":
                system_default = adapter
                continue
            if adapter.probe().get("available"):
                return adapter
        if system_default is not None and system_default.probe().get(
                "available"):
            return system_default
        raise ViewerUnavailable(f"no available viewer consumes {fmt!r}")


def launch(adapter: ViewerAdapter, artifact: Path, *,
           runtime_registry: RuntimeRegistry | None = None,
           ) -> ViewerSession:
    """Start a viewer process. Managed servers (long-running) are
    registered so `stop`/orphan cleanup can track them."""
    probe = adapter.probe()
    if not probe.get("available"):
        raise ViewerUnavailable(
            f"viewer {adapter.descriptor().id} unavailable:"
            f" {probe.get('detail')}")
    argv = adapter.launch_argv(artifact)
    proc = subprocess.Popen(argv)
    managed = "MANAGED_SERVER" in adapter.descriptor().modes
    if managed and runtime_registry is not None:
        runtime_registry.register(RuntimeEntry(
            pid=proc.pid, run_id=f"viewer-{adapter.descriptor().id}",
            command=" ".join(argv)))
    return ViewerSession(viewer_id=adapter.descriptor().id, pid=proc.pid,
                         argv=argv, managed=managed, process=proc)


def stop(session: ViewerSession, *,
         runtime_registry: RuntimeRegistry | None = None) -> None:
    """Terminate a managed session, reap it and drop its registry
    entry. Reaping matters: a zombie child keeps answering signal 0."""
    if session.process is not None:
        session.process.terminate()
        try:
            session.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            session.process.kill()
            session.process.wait(timeout=5)
    else:
        import os
        import signal

        try:
            os.kill(session.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            os.waitpid(session.pid, os.WNOHANG)
        except (ChildProcessError, OSError):
            pass  # not our child anymore — already reaped
    if runtime_registry is not None:
        runtime_registry.unregister(session.pid)
