"""GetHistory use case (V2.4 M3, docs/v2/67 slice 8): run summaries
from the RunLedger as a read model. History is governance input — the
same records `ark gate` and the Control Plane will consume."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from archskillkit.runtime_state.run_ledger import (
    RunLedger,
    RunRecord,
    RunStatus,
)

HISTORY_SCHEMA = "arch-skillkit/history-v1"


class HistoryResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema: Literal["arch-skillkit/history-v1"] = HISTORY_SCHEMA  # type: ignore[assignment]
    total_matching: int
    returned: int
    runs: list[RunRecord] = Field(default_factory=list)


def get_history(ledger: RunLedger, *, limit: int = 50,
                status: RunStatus | None = None) -> HistoryResult:
    runs = ledger.list(limit=None, status=status)
    return HistoryResult(
        total_matching=len(runs),
        returned=min(len(runs), limit),
        runs=runs[:limit],
    )
