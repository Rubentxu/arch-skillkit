"""draw.io viewer: LOCAL_PROCESS with draw.io Desktop when installed
(docs/v2/54 §4). Round-trip editing arrives with the embed-mode
integration (M1 proof, docs/v2/54 §8); this adapter only opens."""

from __future__ import annotations

import shutil
from pathlib import Path

from archskillkit.viewers.contract import (
    ViewerAdapter,
    ViewerCapabilities,
    ViewerDescriptor,
)


def find_drawio_binary() -> str | None:
    return shutil.which("drawio") or shutil.which("draw.io")


class DrawioDesktopViewer(ViewerAdapter):
    def descriptor(self) -> ViewerDescriptor:
        return ViewerDescriptor(
            id="drawio-desktop",
            name="draw.io Desktop",
            consumes=["drawio"],
            modes=["LOCAL_PROCESS"],
            capabilities=ViewerCapabilities(view=True),
            probe={"embed_round_trip": False},
        )

    def probe(self) -> dict:
        binary = find_drawio_binary()
        return {"available": binary is not None,
                "detail": binary or "drawio desktop not found in PATH"}

    def launch_argv(self, artifact: Path) -> list[str]:
        return [find_drawio_binary() or "drawio", str(artifact)]
