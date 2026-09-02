"""Fitness Profile and gate evaluation (V2.4 M3, ADR-0040,
design/schemas/v2.4/fitness-profile.yaml).

Two separable concerns:

- `compute_fitness` MEASURES deterministic dimensions from an open
  world + snapshot. A dimension is pass/warn/fail against thresholds,
  or `na` when the dimension is not instrumented or not applicable
  (N/A is explicit semantics, never hidden as a zero).
- `evaluate_gate` DECIDES: thresholds + active waivers -> verdict and
  exit code. An expired waiver does not excuse the dimension — the
  gate fails and names the expired waiver.

Same inputs -> identical profile and verdict, byte for byte.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from archskillkit.application.models.snapshot import ArchitectureSnapshot
from archskillkit.runtime_state.run_ledger import RunLedger, utcnow
from archskillkit.runtime_state.waivers import WaiverLedger

FITNESS_SCHEMA = "arch-skillkit/fitness-profile-v1"
GATE_SCHEMA = "arch-skillkit/gate-result-v1"

DimensionStatus = Literal["pass", "warn", "fail", "na"]


class Dimension(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: DimensionStatus
    value: float | int | str | None = None
    evidence_refs: list[str] = Field(default_factory=list)


class FitnessThresholds(BaseModel):
    """Gate configuration — lives in the gate, never in the profile."""

    model_config = ConfigDict(extra="forbid")

    min_evidence_coverage: float = Field(default=0.8, ge=0.0, le=1.0)
    max_unknowns: int = Field(default=0, ge=0)
    max_findings: int = Field(default=0, ge=0)
    max_high_severity_findings: int = Field(default=0, ge=0)
    max_run_age_days: int = Field(default=30, ge=0)


class FitnessProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema: Literal["arch-skillkit/fitness-profile-v1"] = FITNESS_SCHEMA  # type: ignore[assignment]
    snapshot_id: str
    dimensions: dict[str, Dimension] = Field(default_factory=dict)
    aggregate: dict | None = None


class GateResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema: Literal["arch-skillkit/gate-result-v1"] = GATE_SCHEMA  # type: ignore[assignment]
    verdict: Literal["pass", "fail"]
    exit_code: int
    snapshot_id: str
    dimensions: dict[str, Dimension]
    waived: list[dict] = Field(default_factory=list)
    failed_dimensions: list[str] = Field(default_factory=list)
    expired_waivers: list[dict] = Field(default_factory=list)


# dimensions not instrumented in V2.4 M3 stay explicitly `na`
_UNINSTRUMENTED = ("projection_validity", "sensor_coverage",
                   "unexplained_change")


def _age_days(started_at: str) -> int | None:
    import datetime as _dt

    try:
        started = _dt.datetime.fromisoformat(started_at)
    except (ValueError, TypeError):
        return None
    now = _dt.datetime.now(_dt.UTC)
    return (now - started).days


def compute_fitness(world, snapshot: ArchitectureSnapshot,
                    thresholds: FitnessThresholds | None = None,
                    ledger: RunLedger | None = None) -> FitnessProfile:
    thresholds = thresholds or FitnessThresholds()
    dims: dict[str, Dimension] = {}

    knowledge = snapshot.knowledge
    has_elements = knowledge is not None and knowledge.elements > 0

    if not has_elements:
        dims["evidence_coverage"] = Dimension(status="na", value=None,
                                              evidence_refs=[
                                                  "no elements"])
        dims["unknown_coverage"] = Dimension(status="na", value=None,
                                             evidence_refs=[
                                                 "no elements"])
    else:
        coverage = knowledge.evidence_coverage
        status = ("pass" if coverage >= thresholds.min_evidence_coverage
                  else "fail")
        dims["evidence_coverage"] = Dimension(
            status=status, value=coverage,
            evidence_refs=["fitness.evidence_coverage"])
        unknowns = knowledge.unknowns
        dims["unknown_coverage"] = Dimension(
            status="pass" if unknowns <= thresholds.max_unknowns
            else "fail",
            value=unknowns, evidence_refs=["fitness.unknowns"])

    findings = world.findings()
    high = sum(1 for f in findings
               if f["data"].get("severity") == "high")
    dims["drift"] = Dimension(
        status="pass" if len(findings) <= thresholds.max_findings
        else "fail",
        value=len(findings), evidence_refs=["fitness.findings"])
    dims["review_debt"] = Dimension(
        status="pass" if high <= thresholds.max_high_severity_findings
        else "fail",
        value=high, evidence_refs=["fitness.high_findings"])

    rules = world.architecture_rules()
    dims["policy_coverage"] = Dimension(
        status="na" if not rules else "pass",
        value=len(rules),
        evidence_refs=[] if not rules else ["fitness.rules"])

    dims["freshness"] = _freshness(ledger, thresholds)

    for name in _UNINSTRUMENTED:
        dims[name] = Dimension(status="na",
                               value="not instrumented in M3")

    return FitnessProfile(snapshot_id=snapshot.snapshot_id,
                          dimensions=dims, aggregate=None)


def _freshness(ledger: RunLedger | None,
               thresholds: FitnessThresholds) -> Dimension:
    if ledger is None:
        return Dimension(status="na", value="no run ledger provided")
    runs = ledger.list(limit=1, status="PASS")
    if not runs:
        return Dimension(status="na", value="no PASS run recorded")
    age = _age_days(runs[0].started_at)
    if age is None:
        return Dimension(status="na", value="unreadable run timestamp")
    return Dimension(status="pass" if age <= thresholds.max_run_age_days
                     else "fail", value=age,
                     evidence_refs=[runs[0].run_id])


def evaluate_gate(world, snapshot: ArchitectureSnapshot,
                  thresholds: FitnessThresholds | None = None,
                  ledger: RunLedger | None = None,
                  waivers: WaiverLedger | None = None) -> GateResult:
    profile = compute_fitness(world, snapshot, thresholds, ledger)
    thresholds = thresholds or FitnessThresholds()
    waivers = waivers or WaiverLedger()
    today = utcnow()[:10]

    waived: list[dict] = []
    expired: list[dict] = []
    failed: list[str] = []
    dims = dict(profile.dimensions)
    for name, dimension in profile.dimensions.items():
        if dimension.status != "fail":
            continue
        active = waivers.active(dimension=name, on_date=today)
        if active:
            dims[name] = dimension.model_copy(update={"status": "warn"})
            waived.append({"dimension": name,
                           "waiver_id": active[0].waiver_id,
                           "expires_at": active[0].expires_at})
            continue
        all_dimension_waivers = [w for w in waivers.list()
                                 if w.dimension == name]
        for w in all_dimension_waivers:
            if w.is_expired(today):
                expired.append({"dimension": name,
                                "waiver_id": w.waiver_id,
                                "expires_at": w.expires_at})
        failed.append(name)

    verdict = "fail" if failed else "pass"
    return GateResult(verdict=verdict, exit_code=0 if verdict == "pass"
                      else 1, snapshot_id=profile.snapshot_id,
                      dimensions=dims, waived=waived,
                      failed_dimensions=failed, expired_waivers=expired)
