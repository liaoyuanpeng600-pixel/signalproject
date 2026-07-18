"""Tests for the Signal type (INV-1, INV-2, INV-3, INV-4, lifecycle)."""

import pytest

from src.core.invariants import Score
from src.core.lifecycle import LifecycleError
from src.core.signals import (
    EntityRef,
    Metadata,
    Signal,
    SignalDirection,
    SignalHorizon,
    SignalStatus,
)


def make_signal(status: SignalStatus = SignalStatus.DRAFT) -> Signal:
    """Helper to create a test Signal."""
    return Signal.create(
        entity_ref=EntityRef(id="entity-1", kind="company"),
        type="earnings",
        claim="ACME reported EPS of $1.20.",
        evidence_ids=("ev-1", "ev-2"),
        direction=SignalDirection.BULLISH,
        horizon=SignalHorizon.SHORT,
        score=Score(magnitude=0.7, confidence=0.9, timeliness=0.8, novelty=0.6, actionability=0.75),
        status=status,
    )


class TestSignalCreate:
    def test_minimal_creation(self) -> None:
        signal = make_signal()
        assert signal.id
        assert signal.entity_ref.id == "entity-1"
        assert signal.type == "earnings"
        assert signal.status == SignalStatus.DRAFT
        assert signal.cluster_id is None
        assert isinstance(signal.metadata, Metadata)

    def test_unique_ids(self) -> None:
        s1 = make_signal()
        s2 = make_signal()
        assert s1.id != s2.id


class TestSignalInvariants:
    def test_inv1_requires_evidence(self) -> None:
        # INV-1: Signal needs at least one Evidence.
        with pytest.raises(ValueError, match="INV-1"):
            Signal.create(
                entity_ref=EntityRef(id="e", kind="company"),
                type="earnings",
                claim="Test.",
                evidence_ids=(),  # No evidence
                direction=SignalDirection.BULLISH,
                horizon=SignalHorizon.SHORT,
                score=Score(0.5, 0.5, 0.5, 0.5, 0.5),
            )

    def test_inv3_provenance_required(self) -> None:
        # INV-3: Signal with provenance_present=False is rejected.
        with pytest.raises(ValueError, match="INV-3"):
            Signal(
                id="sig-1",
                entity_ref=EntityRef(id="e", kind="company"),
                type="earnings",
                claim="Test.",
                evidence_ids=("ev-1",),
                direction=SignalDirection.BULLISH,
                horizon=SignalHorizon.SHORT,
                score=Score(0.5, 0.5, 0.5, 0.5, 0.5),
                provenance_present=False,  # INV-3 violation
            )

    def test_inv4_score_bounds(self) -> None:
        # INV-4 enforced by Score.__post_init__.
        with pytest.raises(ValueError):
            Score(magnitude=1.5, confidence=0.5, timeliness=0.5, novelty=0.5, actionability=0.5)


class TestSignalValidation:
    def test_empty_claim_rejected(self) -> None:
        with pytest.raises(ValueError):
            Signal.create(
                entity_ref=EntityRef(id="e", kind="company"),
                type="earnings",
                claim="",
                evidence_ids=("ev-1",),
                direction=SignalDirection.BULLISH,
                horizon=SignalHorizon.SHORT,
                score=Score(0.5, 0.5, 0.5, 0.5, 0.5),
            )

    def test_claim_too_long_rejected(self) -> None:
        long_claim = "x" * 281  # > 280
        with pytest.raises(ValueError):
            Signal.create(
                entity_ref=EntityRef(id="e", kind="company"),
                type="earnings",
                claim=long_claim,
                evidence_ids=("ev-1",),
                direction=SignalDirection.BULLISH,
                horizon=SignalHorizon.SHORT,
                score=Score(0.5, 0.5, 0.5, 0.5, 0.5),
            )

    def test_timestamp_after_detected_rejected(self) -> None:
        with pytest.raises(ValueError, match="timestamp"):
            Signal.create(
                entity_ref=EntityRef(id="e", kind="company"),
                type="earnings",
                claim="Test.",
                evidence_ids=("ev-1",),
                direction=SignalDirection.BULLISH,
                horizon=SignalHorizon.SHORT,
                score=Score(0.5, 0.5, 0.5, 0.5, 0.5),
                timestamp="2026-07-19T00:00:00+00:00",
                detected_at="2026-07-18T00:00:00+00:00",
            )


class TestSignalLifecycle:
    def test_draft_to_verified(self) -> None:
        sig = make_signal(SignalStatus.DRAFT)
        verified = sig.verify()
        assert verified.status == SignalStatus.VERIFIED
        assert verified.id == sig.id

    def test_verified_to_active(self) -> None:
        sig = make_signal(SignalStatus.VERIFIED)
        active = sig.activate()
        assert active.status == SignalStatus.ACTIVE

    def test_verified_to_held(self) -> None:
        sig = make_signal(SignalStatus.VERIFIED)
        held = sig.hold()
        assert held.status == SignalStatus.HELD

    def test_held_to_active(self) -> None:
        sig = make_signal(SignalStatus.HELD)
        active = sig.promote_from_held()
        assert active.status == SignalStatus.ACTIVE

    def test_active_to_decayed(self) -> None:
        sig = make_signal(SignalStatus.ACTIVE)
        decayed = sig.decay()
        assert decayed.status == SignalStatus.DECAYED
        assert decayed.is_terminal

    def test_active_to_superseded(self) -> None:
        sig = make_signal(SignalStatus.ACTIVE)
        superseded = sig.supersede()
        assert superseded.status == SignalStatus.SUPERSEDED
        assert superseded.is_terminal

    def test_draft_to_rejected(self) -> None:
        sig = make_signal(SignalStatus.DRAFT)
        rejected = sig.reject()
        assert rejected.status == SignalStatus.REJECTED
        assert rejected.is_terminal

    def test_invalid_transition_draft_to_active(self) -> None:
        sig = make_signal(SignalStatus.DRAFT)
        with pytest.raises(LifecycleError):
            sig.activate()  # Must go through VERIFIED first

    def test_invalid_transition_active_to_held(self) -> None:
        sig = make_signal(SignalStatus.ACTIVE)
        with pytest.raises(LifecycleError):
            sig.hold()


class TestSignalImmutability:
    def test_id_immutable(self) -> None:
        sig = make_signal()
        with pytest.raises(Exception):
            sig.id = "new_id"  # type: ignore[misc]

    def test_cannot_modify_status_directly(self) -> None:
        sig = make_signal()
        with pytest.raises(Exception):
            sig.status = SignalStatus.ACTIVE  # type: ignore[misc]


class TestSignalTerminal:
    def test_is_terminal_for_terminal_states(self) -> None:
        assert make_signal(SignalStatus.REJECTED).is_terminal
        assert make_signal(SignalStatus.DECAYED).is_terminal
        assert make_signal(SignalStatus.SUPERSEDED).is_terminal

    def test_is_not_terminal_for_active_states(self) -> None:
        assert not make_signal(SignalStatus.DRAFT).is_terminal
        assert not make_signal(SignalStatus.VERIFIED).is_terminal
        assert not make_signal(SignalStatus.ACTIVE).is_terminal
        assert not make_signal(SignalStatus.HELD).is_terminal
