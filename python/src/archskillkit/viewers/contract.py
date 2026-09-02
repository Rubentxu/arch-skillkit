"""Viewer contracts (docs/v2/54 §3/§6, design/schemas/v2.4/
viewer-descriptor.yaml).

A descriptor is data: registries, routers, doctor and the future
Control Plane consume it without importing adapter implementations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

VIEWER_DESCRIPTOR_SCHEMA = "arch-skillkit/viewer-descriptor-v1"

ViewerMode = Literal[
    "EMBEDDED", "MANAGED_SERVER", "LOCAL_PROCESS", "WEB_HANDOFF",
]

ALL_FORMATS = ("likec4", "arrows", "graphml", "jsoncanvas", "drawio")


class ViewerCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid")

    view: bool
    edit: bool = False
    round_trip: bool = False
    autosave: bool = False
    semantic_links: bool = False


class ViewerDescriptor(BaseModel):
    """No `schema` field: the descriptor is a contract object, not a
    command output — wire outputs carry their schema id in the envelope
    (docs/v2/55 §4). Matches the design schema exactly."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    consumes: list[str] = Field(default_factory=list)
    modes: list[ViewerMode] = Field(default_factory=list)
    capabilities: ViewerCapabilities
    probe: dict = Field(default_factory=dict)


class ViewerUnavailable(LookupError):
    """Stable error code per docs/v2/55 §10."""

    code = "VIEWER_UNAVAILABLE"


class ViewerAdapter:
    """Base class for viewers: descriptor + probe + launch plan.

    `launch_argv` returns the command that would open the artifact —
    building it is pure and testable; running it is `viewers.launch`.
    """

    def descriptor(self) -> ViewerDescriptor:  # pragma: no cover - iface
        raise NotImplementedError

    def probe(self) -> dict:  # pragma: no cover - iface
        raise NotImplementedError

    def launch_argv(self, artifact: Path) -> list[str]:  # pragma: no cover
        raise NotImplementedError
