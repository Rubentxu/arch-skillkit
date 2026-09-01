"""SensorContract (docs/v2/45 §2.2, V2.3-F5).

Scanner rules describe the architectural fact they detect instead of the
interpreter guessing from rule names: classification connascence with
check_id substrings is gone. A rule opts in via metadata:

    metadata:
      archskillkit:
        fact: publishes          # semantic predicate (edge kind PUBLISHES)
        target_kind: topic       # pseudo-symbol kind of the target
        target_metavar: $TOPIC   # optional: metavar holding the target
        cardinality: many        # one | many (contradiction gate)
        confidence: high

Rules without the block keep working through the legacy bridge
(`classify_legacy`) until every pack is migrated.
"""

from __future__ import annotations

from dataclasses import dataclass

SENSOR_METADATA_KEY = "archskillkit"
CARDINALITIES = ("one", "many")


class ContractError(Exception):
    """A rule declared an invalid archskillkit metadata block."""


@dataclass(frozen=True)
class SensorContract:
    rule_id: str
    fact: str
    target_kind: str
    target_metavar: str | None = None
    cardinality: str = "many"
    confidence: str = "high"

    @property
    def edge_kind(self) -> str:
        return self.fact.upper()

    @classmethod
    def from_metadata(cls, rule_id: str,
                      metadata: dict | None) -> SensorContract | None:
        """Parse the archskillkit block; None when the rule has none."""
        block = (metadata or {}).get(SENSOR_METADATA_KEY) or {}
        if not block:
            return None
        missing = [key for key in ("fact", "target_kind")
                   if not block.get(key)]
        if missing:
            raise ContractError(
                f"rule {rule_id!r}: archskillkit metadata is missing "
                f"{', '.join(missing)}")
        cardinality = str(block.get("cardinality", "many")).lower()
        if cardinality not in CARDINALITIES:
            raise ContractError(
                f"rule {rule_id!r}: cardinality must be one of "
                f"{CARDINALITIES}, got {cardinality!r}")
        target_metavar = block.get("target_metavar")
        if target_metavar is not None and not target_metavar.startswith("$"):
            raise ContractError(
                f"rule {rule_id!r}: target_metavar must be a metavar "
                f"like $TOPIC, got {target_metavar!r}")
        return cls(rule_id=rule_id,
                   fact=str(block["fact"]).strip().lower(),
                   target_kind=str(block["target_kind"]),
                   target_metavar=target_metavar,
                   cardinality=cardinality,
                   confidence=str(block.get("confidence", "high")))


# Legacy bridge (deprecated): check_id family → (edge kind, target kind).
# Kept only for payloads captured before packs declared contracts.
LEGACY_EDGE_RULES: tuple[tuple[str, str, str], ...] = (
    ("messaging.listener", "CONSUMES", "topic"),
    ("persistence.repository", "USES", "datastore"),
    ("http.client", "USES", "http_client"),
    ("endpoint", "EXPOSES", "endpoint"),
)


def classify_legacy(check_id: str) -> tuple[str, str] | None:
    for pattern, edge_kind, target_kind in LEGACY_EDGE_RULES:
        if pattern in check_id:
            return edge_kind, target_kind
    return None


# Static cardinality defaults (promotion behavior); contracts registered
# by an ingest take precedence over these for their own fact.
PREDICATE_CARDINALITY: dict[str, str] = {
    "belongs_to": "one",
    "part_of": "one",
    "deployed_on": "one",
    "implemented_by": "many",
    "depends_on": "many",
    "uses": "many",
    "exposes": "many",
    "publishes": "many",
    "consumes": "many",
    "reads": "many",
    "writes": "many",
    "calls": "many",
}

_registered: dict[str, SensorContract] = {}


def register(contract: SensorContract) -> None:
    _registered[contract.rule_id] = contract


def contract_for_rule(rule_id: str) -> SensorContract | None:
    return _registered.get(rule_id)


def clear_registered() -> None:
    """Test isolation hook — registration is per-interpreter state."""
    _registered.clear()


def cardinality_for_predicate(predicate: str) -> str:
    """Registered contracts win for their fact; static defaults next;
    unknown predicates default to `many` (never accidental contradictions)."""
    normalized = predicate.strip().lower()
    for contract in _registered.values():
        if contract.fact == normalized:
            return contract.cardinality
    return PREDICATE_CARDINALITY.get(normalized, "many")
