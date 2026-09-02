"""Read-side port for query use cases (V2.4 M0, docs/v2/67 slice 2).

Consumers (GetStatus, Explain, future MCP/HTTP adapters) depend on this
Protocol — never on `world.graph` outside the domain boundary (M0 gate).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ArchitectureQueryPort(Protocol):
    """Read surface of the Architecture World."""

    project_id: str
    project_name: str
    root: str

    def snapshot(self) -> dict: ...
    def last_event_id(self) -> str: ...

    def find_objects(self, obj_type: str, **data_match) -> list[dict]: ...
    def get_object(self, object_id: str) -> dict: ...

    def architecture_relations(self) -> list[dict]: ...
    def claim_observation_ids(self, claim_id: str) -> list[str]: ...
    def claim_is_contradicted(self, claim_id: str) -> bool: ...
