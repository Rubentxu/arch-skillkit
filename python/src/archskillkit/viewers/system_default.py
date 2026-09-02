"""SystemDefaultViewer (docs/v2/54 §5): open the artifact with the OS
association (`xdg-open` / `open` / explorer). Unknown applications are
never turned into domain dependencies — the OS decides."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from archskillkit.viewers.contract import (
    ALL_FORMATS,
    ViewerAdapter,
    ViewerCapabilities,
    ViewerDescriptor,
)

_COMMANDS = (("darwin", "open"), ("win32", "explorer"))


def _open_command() -> str | None:
    for sysname, command in _COMMANDS:
        if sys.platform == sysname:
            return command if shutil.which(command) else None
    return shutil.which("xdg-open")


class SystemDefaultViewer(ViewerAdapter):
    """Last link of every route: LOCAL_PROCESS via OS association."""

    def descriptor(self) -> ViewerDescriptor:
        return ViewerDescriptor(
            id="system-default",
            name="System default application",
            consumes=list(ALL_FORMATS),
            modes=["LOCAL_PROCESS"],
            capabilities=ViewerCapabilities(view=True),
        )

    def probe(self) -> dict:
        command = _open_command()
        return {"available": command is not None,
                "detail": command or "no OS open command found"}

    def launch_argv(self, artifact: Path) -> list[str]:
        if sys.platform == "win32":
            return ["explorer", str(artifact)]
        return [os.environ.get("ARK_OPEN_CMD", _open_command() or "xdg-open"),
                str(artifact)]
