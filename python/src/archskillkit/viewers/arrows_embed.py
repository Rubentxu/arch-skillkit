"""Arrows embed viewer adapter (V2.4 M5 slice 26).

Consumes the arrows projection format and opens it via the embedded
Arrows.app bundle served from the vendor directory.
"""

from __future__ import annotations

from pathlib import Path

from archskillkit.ids import arch_data_root
from archskillkit.viewers.contract import (
    ViewerAdapter,
    ViewerCapabilities,
    ViewerDescriptor,
)

# Vendor dir: <data-root>/vendor/arrows/
VENDOR_DIR = arch_data_root() / "vendor" / "arrows"

# Required files for the embed bundle to be considered available
_REQUIRED_FILES = ("embed.html",)


def _vendor_path(*parts: str) -> Path:
    return VENDOR_DIR.joinpath(*parts)


def _bundle_available() -> tuple[bool, str]:
    """Check if the Arrows embed bundle is present in the vendor dir."""
    if not VENDOR_DIR.is_dir():
        return False, f"vendor dir not found: {VENDOR_DIR}"
    missing = [f for f in _REQUIRED_FILES if not _vendor_path(f).is_file()]
    if missing:
        return False, f"missing files: {', '.join(missing)}"
    return True, "ok"


class ArrowsEmbedViewer(ViewerAdapter):
    """Embedded Arrows.app viewer via vendor bundle.

    Serves the Arrows.app embed bundle (Apache-2.0, built from
    neo4j-labs/arrows.app) from the local vendor directory and
    communicates via the bridge postMessage protocol documented in
    src/embed/bridge/bridge.ts.
    """

    def descriptor(self) -> ViewerDescriptor:
        return ViewerDescriptor(
            id="arrows-embed",
            name="Arrows embedded viewer",
            consumes=["arrows"],
            modes=["EMBEDDED"],
            capabilities=ViewerCapabilities(view=True, edit=False, round_trip=False),
        )

    def probe(self) -> dict:
        available, detail = _bundle_available()
        return {"available": available, "detail": detail}

    def launch_argv(self, artifact: Path) -> list[str]:
        # For an embedded viewer the artifact path is informational;
        # the shell loads the embed.html from the vendor dir and
        # fetches the artifact data via /arrows-artifact.
        return [str(artifact)]
