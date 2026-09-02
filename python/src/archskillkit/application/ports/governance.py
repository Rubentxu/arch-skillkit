"""Governance read port (V2.4 M0, ADR-0045).

Read-only governance surface: rules, findings and proposals. Mutations
(promote, waiver) arrive later as explicit commands with their own port
and are never inferred from read access.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class GovernancePort(Protocol):
    def architecture_rules(self) -> list[dict]: ...
    def findings(self) -> list[dict]: ...
    def proposals(self) -> list[dict]: ...
