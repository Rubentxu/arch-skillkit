"""Admin gate for delivery adapters (V2.4 M4, docs/v2/59 M4 acceptance:
"admin disabled by default").

Admin is OFF unless the operator opts in. Two equivalent opt-ins:
- environment variable ARCH_SKILLKIT_ADMIN=1 (or true / yes)
- the `--admin` CLI flag on the MCP server (or any delivery
  adapter that wants to expose admin tools)

The gate is the single source of truth across delivery adapters.
Any new admin tool MUST be added to ADMIN_TOOLS and MUST be
gated through require_admin() before doing any work — listing
the tool and refusing the call is defence in depth, not a
substitute for the explicit require_admin() call.

Refusals carry the stable error code ADMIN_DISABLED so consumers
(bots, CI, LLM agents) can branch on the code without parsing
free-form text.
"""

from __future__ import annotations

import os
from typing import Final

ADMIN_DISABLED_CODE: Final = "ADMIN_DISABLED"

# Admin tool names. Adding a new admin tool means adding it here
# AND wiring the gate in the delivery adapter.
ADMIN_TOOLS: Final = (
    "arch_propose_list",
    "arch_propose_create",
    "arch_propose_diff",
    "arch_propose_review",
    "arch_propose_promote",
    "arch_propose_reject",
    "arch_prompt_registry",
    "arch_skill_registry",
    "arch_simulate",
)


class AdminDisabledError(Exception):
    """Raised when an admin tool is called while the gate is off.

    Carries a stable error code so consumers do not have to parse
    free-form text."""

    code: str = ADMIN_DISABLED_CODE

    def __init__(self, message: str = "admin disabled") -> None:
        super().__init__(message)
        self.message = message

    def to_envelope(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


def admin_enabled(cli_flag: bool = False) -> bool:
    """Return True iff admin is opted in via env or CLI flag.

    Precedence: CLI flag beats env var. Env var accepts any of
    "1", "true", "yes" (case-insensitive)."""
    if cli_flag:
        return True
    raw = os.environ.get("ARCH_SKILLKIT_ADMIN", "").strip().lower()
    return raw in {"1", "true", "yes"}


def require_admin(enabled: bool, tool_name: str) -> None:
    """Raise AdminDisabledError if admin is off and tool is admin.

    Use this in every admin tool handler before doing work — the
    listing gate alone is not enough (a client could call a tool
    without listing first)."""
    if tool_name in ADMIN_TOOLS and not enabled:
        raise AdminDisabledError(
            f"tool {tool_name!r} requires admin opt-in; set ARCH_SKILLKIT_ADMIN=1 or pass --admin"
        )
