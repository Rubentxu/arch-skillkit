"""Waiver ledger (V2.4 M3, docs/v2/58 "waivers/debt ledger").

A waiver excuses one fitness dimension for a bounded period. Governance
records live under the XDG state root — separate from the world (they
are policy decisions, not architecture knowledge) and separate from
runtime state (they outlive processes).

Expiry semantics (M3 gate): an expired waiver does NOT excuse its
dimension — the configured gate fails on an expired waiver exactly as
if no waiver existed, with the expiry surfaced in the result.
"""

from __future__ import annotations

import datetime as dt
import fcntl
import json
import os
import uuid
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from archskillkit.ids import arch_state_root
from archskillkit.runtime_state.run_ledger import utcnow

WAIVER_SCHEMA = "arch-skillkit/waiver-v1"


class Waiver(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema: str = WAIVER_SCHEMA
    waiver_id: str
    dimension: str
    reason: str
    granted_by: str
    created_at: str
    expires_at: str  # ISO date (YYYY-MM-DD, UTC)

    def is_expired(self, on_date: str | None = None) -> bool:
        day = on_date or dt.datetime.now(dt.UTC).date().isoformat()
        return self.expires_at < day


class WaiverLedger:
    def __init__(self, root: Path | None = None):
        self.root = root or arch_state_root()
        self.path = self.root / "waivers.json"

    # ---- locked, atomic IO ---------------------------------------------

    def _read_locked(self, fh) -> dict[str, Waiver]:
        fh.seek(0)
        raw = fh.read().strip()
        if not raw:
            return {}
        doc = json.loads(raw)
        return {w["waiver_id"]: Waiver(**w) for w in doc.get("waivers", [])}

    def _write_locked(self, fh, waivers: dict[str, Waiver]) -> None:
        fh.seek(0)
        fh.truncate()
        fh.write(json.dumps(
            {"version": 1,
             "waivers": [w.model_dump() for w in waivers.values()]},
            indent=2) + "\n")
        fh.flush()
        os.fsync(fh.fileno())

    def _mutate(self, fn):
        self.root.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a+") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                waivers = fn(self._read_locked(fh))
                self._write_locked(fh, waivers)
                return waivers
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)

    # ---- API ------------------------------------------------------------

    def grant(self, dimension: str, reason: str, granted_by: str,
              expires_at: str) -> Waiver:
        waiver = Waiver(
            waiver_id=f"waiv-{uuid.uuid4().hex[:12]}",
            dimension=dimension, reason=reason, granted_by=granted_by,
            created_at=utcnow(), expires_at=expires_at)

        def add(waivers: dict[str, Waiver]) -> dict[str, Waiver]:
            waivers[waiver.waiver_id] = waiver
            return waivers

        self._mutate(add)
        return waiver

    def active(self, dimension: str | None = None,
               on_date: str | None = None) -> list[Waiver]:
        waivers = sorted(self._mutate(lambda w: w).values(),
                         key=lambda w: w.expires_at)
        out = []
        for waiver in waivers:
            if waiver.is_expired(on_date):
                continue
            if dimension is not None and waiver.dimension != dimension:
                continue
            out.append(waiver)
        return out

    def list(self, include_expired: bool = True) -> list[Waiver]:
        waivers = sorted(self._mutate(lambda w: w).values(),
                         key=lambda w: w.waiver_id)
        if include_expired:
            return waivers
        return [w for w in waivers if not w.is_expired()]
