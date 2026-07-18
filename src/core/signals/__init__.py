"""
Signal type per Object Model §4.

A Signal is a discrete, evidenced observation about an Entity. It has a
lifecycle (draft → verified → active → decayed | superseded | rejected) and
is the atomic unit of observation.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum

from src.core.entities import Entity
from src.core.ids import ID, new_id
from src.core.invariants import Score, assert_inv_1, assert_inv_3, assert_inv_4
from src.core.lifecycle import SIGNAL_LIFECYCLE, SignalStatus, assert_transition
from src.core.timestamps import now_utc


class SignalDirection(str, Enum):
    """Directional implication of a Signal."""

    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class SignalHorizon(str, Enum):
    """Time horizon over which a Signal's effect persists."""

    INTRADAY = "intraday"  # <1 trading day
    SHORT = "short"  # 1–30 trading days
    MEDIUM = "medium"  # 30–180 trading days
    LONG = "long"  # >180 trading days


# Reference to an Entity without holding the full Entity object.
# Used in Signal.entity_ref to avoid circular dependencies.


@dataclass(frozen=True, slots=True)
class EntityRef:
    """A reference to an Entity.

    The id here is the Entity's id. We use a lightweight ref to avoid
    embedding the full Entity in every Signal.
    """

    id: ID
    kind: str  # The EntityKind value as a string for serialization


@dataclass(frozen=True, slots=True)
class Metadata:
    """Free-form but typed metadata bag attached to a Signal.

    Per Workflow Model, used for provenance flags, override state, etc.
    """

    source_doc_id: ID | None = None
    cluster_size: int | None = None
    burst_triggered: bool = False
    reasoning_skipped: bool = False
    reasoning_partial: bool = False
    score_partial: bool = False
    degrade_mode: bool = False
    override_active: bool = False
    precedent_basis: str | None = None
    precedent_conflict: bool = False
    custom_tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Signal:
    """A discrete, evidenced observation about an Entity.

    Frozen: id is immutable (INV-2). Status transitions are validated
    against SIGNAL_LIFECYCLE.
    """

    id: ID
    entity_ref: EntityRef
    type: str  # SignalType enum value as string (10 types per 10_signal_taxonomy)
    claim: str  # 1–280 chars, falsifiable
    evidence_ids: tuple[ID, ...]  # ≥1 Evidence (INV-1)
    direction: SignalDirection
    horizon: SignalHorizon
    score: Score  # INV-4 enforced in Score.__post_init__
    status: SignalStatus = SignalStatus.DRAFT
    timestamp: str = field(default_factory=now_utc)  # When underlying event occurred
    detected_at: str = field(default_factory=now_utc)  # When system emitted the Signal
    cluster_id: ID | None = None
    metadata: Metadata = field(default_factory=Metadata)
    provenance_present: bool = True  # For INV-3 check

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("Signal.id is required")
        if not self.claim:
            raise ValueError("Signal.claim is required")
        if len(self.claim) > 280:
            raise ValueError(f"Signal.claim exceeds 280 chars: {len(self.claim)}")
        if self.timestamp > self.detected_at:
            raise ValueError(
                f"Signal.timestamp ({self.timestamp}) cannot be after detected_at ({self.detected_at})"
            )
        # INV-1: at least one Evidence
        if len(self.evidence_ids) < 1:
            raise ValueError(
                f"INV-1 violation: Signal has {len(self.evidence_ids)} Evidence objects; requires ≥1"
            )
        # INV-3: Provenance present
        if not self.provenance_present:
            raise ValueError("INV-3 violation: Signal is missing Provenance")
        # INV-4: Score values in [0, 1] (also enforced by Score, but explicit)
        assert_inv_4(self.score)

    def transition(self, new_status: SignalStatus) -> "Signal":
        """Transition to a new status. Validates against SIGNAL_LIFECYCLE.

        Raises:
            LifecycleError: If the transition is not allowed.
        """
        assert_transition(SIGNAL_LIFECYCLE, self.status, new_status)
        return replace(self, status=new_status)

    def verify(self) -> "Signal":
        """Promote a draft Signal to verified."""
        return self.transition(SignalStatus.VERIFIED)

    def activate(self) -> "Signal":
        """Promote a verified Signal to active."""
        return self.transition(SignalStatus.ACTIVE)

    def hold(self) -> "Signal":
        """Hold a verified Signal for curator review."""
        return self.transition(SignalStatus.HELD)

    def reject(self) -> "Signal":
        """Reject the Signal. Terminal."""
        return self.transition(SignalStatus.REJECTED)

    def decay(self) -> "Signal":
        """Mark the Signal as decayed. Terminal."""
        return self.transition(SignalStatus.DECAYED)

    def supersede(self) -> "Signal":
        """Mark the Signal as superseded. Terminal."""
        return self.transition(SignalStatus.SUPERSEDED)

    def promote_from_held(self) -> "Signal":
        """Promote a held Signal to active (curator decision)."""
        return self.transition(SignalStatus.ACTIVE)

    @property
    def is_terminal(self) -> bool:
        """True if the Signal is in a terminal state (rejected, decayed, superseded)."""
        return self.status in {SignalStatus.REJECTED, SignalStatus.DECAYED, SignalStatus.SUPERSEDED}

    @classmethod
    def create(
        cls,
        entity_ref: EntityRef,
        type: str,
        claim: str,
        evidence_ids: tuple[ID, ...],
        direction: SignalDirection,
        horizon: SignalHorizon,
        score: Score,
        id: ID | None = None,
        status: SignalStatus = SignalStatus.DRAFT,
        timestamp: str | None = None,
        detected_at: str | None = None,
        cluster_id: ID | None = None,
        metadata: Metadata | None = None,
    ) -> "Signal":
        """Factory method to create a new Signal."""
        kwargs: dict = {
            "id": id if id is not None else new_id(),
            "entity_ref": entity_ref,
            "type": type,
            "claim": claim,
            "evidence_ids": evidence_ids,
            "direction": direction,
            "horizon": horizon,
            "score": score,
            "status": status,
            "cluster_id": cluster_id,
            "metadata": metadata or Metadata(),
        }
        if timestamp is not None:
            kwargs["timestamp"] = timestamp
        if detected_at is not None:
            kwargs["detected_at"] = detected_at
        return cls(**kwargs)
