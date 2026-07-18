"""
System-wide invariants for SIGNAL.

Each invariant is a check that can be run against an Object (or a set of
Objects). Invariants are organized per the 12 rules in INVARIANTS.md.

INVARIANT CATALOG (cross-referenced to INVARIANTS.md):

- INV-1: Evidence required on Signal
- INV-2: Signal ID immutable (enforced by dataclass(frozen=True))
- INV-3: Provenance mandatory (fields present)
- INV-4: Score values bounded [0,1]
- INV-5: Composite deterministic (formula check)
- INV-6: Lifecycle transitions valid (lifecycle.assert_transition)
- INV-7: Schema authority unique (docs concern)
- INV-8: Draft signals never reach users (runtime concern)
- INV-9: cycle_id is ULID (validated at format level)
- INV-10: Times are ISO8601 UTC (timestamps module)
- INV-11: OverrideRecord append-only (data structure)
- INV-12: Composite weight sum 1.0 (formula check)
"""

from __future__ import annotations

from dataclasses import dataclass

# INV-12: Composite weight sum must equal 1.0.
# The five weights are the canonical formula from 06_scoring_framework §4.
COMPOSITE_WEIGHTS = {
    "magnitude": 0.30,
    "confidence": 0.25,
    "timeliness": 0.20,
    "novelty": 0.15,
    "actionability": 0.10,
}
COMPOSITE_WEIGHT_SUM = sum(COMPOSITE_WEIGHTS.values())  # 1.0
COMPOSITE_WEIGHT_SUM_TOLERANCE = 1e-9


def assert_composite_weights_sum_to_one() -> None:
    """INV-12: Validate that the canonical composite weights sum to 1.0.

    Raises:
        AssertionError: If the weights do not sum to 1.0 (within tolerance).
    """
    total = sum(COMPOSITE_WEIGHTS.values())
    assert abs(total - 1.0) < COMPOSITE_WEIGHT_SUM_TOLERANCE, (
        f"INV-12 violation: composite weights sum to {total}, expected 1.0"
    )


@dataclass(frozen=True)
class Score:
    """The 5-dimension Score for a Signal (INV-4 compliant).

    All values MUST be in [0.0, 1.0]. Composite is computed deterministically
    per INV-5 (formula in 06_scoring_framework §4).
    """

    magnitude: float
    confidence: float
    timeliness: float
    novelty: float
    actionability: float

    def __post_init__(self) -> None:
        """INV-4: All score dimensions must be in [0.0, 1.0]."""
        for field_name in (
            "magnitude",
            "confidence",
            "timeliness",
            "novelty",
            "actionability",
        ):
            value = getattr(self, field_name)
            if not (0.0 <= value <= 1.0):
                raise ValueError(
                    f"INV-4 violation: {field_name}={value} not in [0.0, 1.0]"
                )

    @property
    def composite(self) -> float:
        """INV-5: Composite is the deterministic weighted sum.

        Rounded to 4 decimal places per Workflow Model.
        """
        raw = (
            COMPOSITE_WEIGHTS["magnitude"] * self.magnitude
            + COMPOSITE_WEIGHTS["confidence"] * self.confidence
            + COMPOSITE_WEIGHTS["timeliness"] * self.timeliness
            + COMPOSITE_WEIGHTS["novelty"] * self.novelty
            + COMPOSITE_WEIGHTS["actionability"] * self.actionability
        )
        return round(raw, 4)


def assert_inv_4(score: Score) -> None:
    """INV-4: Score values are bounded [0, 1]."""
    for field_name in ("magnitude", "confidence", "timeliness", "novelty", "actionability"):
        value = getattr(score, field_name)
        if not (0.0 <= value <= 1.0):
            raise AssertionError(
                f"INV-4 violation: {field_name}={value} not in [0.0, 1.0]"
            )


def assert_inv_1(evidence_count: int) -> None:
    """INV-1: Every Signal has non-empty Evidence (≥1)."""
    if evidence_count < 1:
        raise AssertionError(
            f"INV-1 violation: Signal has {evidence_count} Evidence objects; requires ≥1"
        )


def assert_inv_3(provenance_present: bool) -> None:
    """INV-3: Every Signal has complete Provenance."""
    if not provenance_present:
        raise AssertionError("INV-3 violation: Signal is missing Provenance")


def assert_inv_9(cycle_id: str) -> None:
    """INV-9: cycle_id format check.

    Phase 1 uses UUIDv4 strings; this is a permissive check. Once ULID is
    introduced, the strict check is: 26 chars, Crockford base32, time-prefixed.
    """
    if not isinstance(cycle_id, str) or len(cycle_id) == 0:
        raise AssertionError(f"INV-9 violation: cycle_id {cycle_id!r} is not a non-empty string")


def assert_inv_10(timestamp: str) -> None:
    """INV-10: Times are ISO8601 UTC.

    Delegates to timestamps.is_valid_iso8601_utc.
    """
    from src.core.timestamps import is_valid_iso8601_utc

    if not is_valid_iso8601_utc(timestamp):
        raise AssertionError(f"INV-10 violation: timestamp {timestamp!r} is not ISO8601 UTC")
