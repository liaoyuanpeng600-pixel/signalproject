"""Tests for SignalPromoter (Phase 5 Checkpoint 1)."""

import pytest

from src.core.entities import Entity, EntityKind
from src.core.ids import ID
from src.core.invariants import Score
from src.core.lifecycle import SignalStatus
from src.core.signals import EntityRef, Signal, SignalDirection, SignalHorizon
from src.research.promotion import (
    BORDERLINE_LOW,
    HIGH_CONFIDENCE_THRESHOLD,
    REJECTION_THRESHOLD,
    PromotionDecision,
    PromotionPolicy,
    SignalPromoter,
)


def _score(value: float) -> Score:
    return Score(
        magnitude=value,
        confidence=value,
        timeliness=value,
        novelty=value,
        actionability=value,
    )


def _signal(
    *,
    status: SignalStatus,
    composite: float = 0.7,
    signal_id: str = "s-1",
) -> Signal:
    return Signal.create(
        entity_ref=EntityRef(id="e-1", kind="company"),
        type="capital_action",
        claim="claim",
        evidence_ids=(ID("ev-1"),),
        direction=SignalDirection.BULLISH,
        horizon=SignalHorizon.SHORT,
        score=_score(composite),
        status=status,
        id=ID(signal_id),
    )


# ----------------------- policy -----------------------


class TestPromotionPolicy:
    def test_defaults(self) -> None:
        p = PromotionPolicy()
        assert p.high_confidence_threshold == HIGH_CONFIDENCE_THRESHOLD
        assert p.borderline_low == BORDERLINE_LOW
        assert p.rejection_threshold == REJECTION_THRESHOLD

    def test_invalid_ordering(self) -> None:
        with pytest.raises(ValueError):
            PromotionPolicy(
                rejection_threshold=0.5,
                borderline_low=0.3,
                high_confidence_threshold=0.8,
            )

    def test_out_of_range(self) -> None:
        with pytest.raises(ValueError):
            PromotionPolicy(rejection_threshold=-0.1)


# ----------------------- VERIFIED -> {ACTIVE, HELD, REJECTED} -----------------------


class TestVerifiedPromotion:
    def test_high_composite_promotes_to_active(self) -> None:
        promoter = SignalPromoter()
        sig = _signal(status=SignalStatus.VERIFIED, composite=0.8)
        d = promoter.evaluate(sig)
        assert d.target == SignalStatus.ACTIVE
        assert d.should_transition is True

    def test_borderline_holds(self) -> None:
        promoter = SignalPromoter()
        sig = _signal(status=SignalStatus.VERIFIED, composite=0.5)
        d = promoter.evaluate(sig)
        assert d.target == SignalStatus.HELD
        assert d.should_transition is True

    def test_low_composite_rejects(self) -> None:
        promoter = SignalPromoter()
        sig = _signal(status=SignalStatus.VERIFIED, composite=0.2)
        d = promoter.evaluate(sig)
        assert d.target == SignalStatus.REJECTED

    def test_threshold_boundary_active(self) -> None:
        """Composite exactly at high_confidence_threshold promotes to ACTIVE."""
        promoter = SignalPromoter()
        sig = _signal(status=SignalStatus.VERIFIED, composite=HIGH_CONFIDENCE_THRESHOLD)
        d = promoter.evaluate(sig)
        assert d.target == SignalStatus.ACTIVE


# ----------------------- ACTIVE -> {DECAYED, HELD, retained} -----------------------


class TestActiveDemotion:
    def test_high_composite_retained(self) -> None:
        promoter = SignalPromoter()
        sig = _signal(status=SignalStatus.ACTIVE, composite=0.9)
        d = promoter.evaluate(sig)
        assert d.target == SignalStatus.ACTIVE
        assert d.should_transition is False

    def test_borderline_decays(self) -> None:
        """ACTIVE borderline signals must DECAY (cannot transition to HELD
        per SIGNAL_LIFECYCLE; ACTIVE -> {DECAYED, SUPERSEDED})."""
        promoter = SignalPromoter()
        sig = _signal(status=SignalStatus.ACTIVE, composite=0.4)
        d = promoter.evaluate(sig)
        assert d.target == SignalStatus.DECAYED

    def test_very_low_decays(self) -> None:
        promoter = SignalPromoter()
        sig = _signal(status=SignalStatus.ACTIVE, composite=0.1)
        d = promoter.evaluate(sig)
        assert d.target == SignalStatus.DECAYED


# ----------------------- passthrough states -----------------------


class TestPassthroughStates:
    def test_draft_passthrough(self) -> None:
        promoter = SignalPromoter()
        sig = _signal(status=SignalStatus.DRAFT)
        d = promoter.evaluate(sig)
        assert d.target == SignalStatus.DRAFT
        assert d.should_transition is False
        assert "draft" in d.reason

    def test_held_passthrough(self) -> None:
        promoter = SignalPromoter()
        sig = _signal(status=SignalStatus.HELD)
        d = promoter.evaluate(sig)
        assert d.target == SignalStatus.HELD
        assert d.should_transition is False
        assert "curator" in d.reason

    def test_terminal_states_passthrough(self) -> None:
        promoter = SignalPromoter()
        for terminal in {
            SignalStatus.REJECTED,
            SignalStatus.DECAYED,
            SignalStatus.SUPERSEDED,
        }:
            sig = _signal(status=terminal)
            d = promoter.evaluate(sig)
            assert d.target == terminal
            assert d.should_transition is False


# ----------------------- batch -----------------------


class TestBatchEvaluation:
    def test_evaluate_many_returns_tuple(self) -> None:
        promoter = SignalPromoter()
        sigs = (
            _signal(status=SignalStatus.VERIFIED, composite=0.8, signal_id="s-1"),
            _signal(status=SignalStatus.VERIFIED, composite=0.5, signal_id="s-2"),
            _signal(status=SignalStatus.VERIFIED, composite=0.1, signal_id="s-3"),
        )
        decisions = promoter.evaluate_many(sigs)
        assert len(decisions) == 3
        targets = [d.target for d in decisions]
        assert targets == [
            SignalStatus.ACTIVE,
            SignalStatus.HELD,
            SignalStatus.REJECTED,
        ]


# ----------------------- custom policy -----------------------


class TestCustomPolicy:
    def test_strict_policy_rejects_more(self) -> None:
        policy = PromotionPolicy(
            high_confidence_threshold=0.9,
            borderline_low=0.7,
            rejection_threshold=0.5,
        )
        promoter = SignalPromoter(policy=policy)
        sig = _signal(status=SignalStatus.VERIFIED, composite=0.8)
        d = promoter.evaluate(sig)
        # 0.8 is below 0.9 (high) and above 0.7 (borderline) → HELD.
        assert d.target == SignalStatus.HELD


# ----------------------- decision properties -----------------------


class TestDecisionProperties:
    def test_should_transition_true_when_target_differs(self) -> None:
        promoter = SignalPromoter()
        sig = _signal(status=SignalStatus.VERIFIED, composite=0.8)
        d = promoter.evaluate(sig)
        assert d.original.id == sig.id
        assert d.should_transition is True

    def test_should_transition_false_when_target_same(self) -> None:
        promoter = SignalPromoter()
        sig = _signal(status=SignalStatus.ACTIVE, composite=0.9)
        d = promoter.evaluate(sig)
        assert d.should_transition is False