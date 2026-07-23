"""
Signal promotion / demotion — Phase 5 Checkpoint 1.

`SignalPromoter` applies the Phase 5 promotion/demotion rules to a batch
of Signals. The rules align with the Scoring Framework §5 zones:

- VERIFIED -> ACTIVE: composite >= 0.65 (high-confidence band).
- VERIFIED -> HELD:    0.45 <= composite < 0.65 (borderline band) — held
                       for curator review.
- ACTIVE -> DECAYED:   composite < 0.30 OR signal age exceeds horizon.
- ACTIVE -> HELD:      composite in [0.30, 0.45) — borderline drop.
- VERIFIED with composite < 0.30 -> REJECTED.

The promoter is pure: it does NOT persist transitions. It returns
`PromotionDecision` objects; the caller (`KnowledgeUpdater`) persists them
via `persistence.lifecycle` helpers.

Dependency rules:
- Depends on `core.types` and `persistence.lifecycle` helpers.
- Does NOT import runtime.* internals.
- Does NOT import workflow gates.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from src.core.invariants import Score
from src.core.lifecycle import SignalStatus
from src.core.signals import Signal
from src.core.timestamps import now_utc


# Scoring Framework §5 zones. Promoter policy mirrors these.
HIGH_CONFIDENCE_THRESHOLD = 0.65
BORDERLINE_LOW = 0.45
REJECTION_THRESHOLD = 0.30


@dataclass(frozen=True, slots=True)
class PromotionPolicy:
    """Configurable thresholds for promotion/demotion.

    Defaults align with Scoring Framework §5.
    """

    high_confidence_threshold: float = HIGH_CONFIDENCE_THRESHOLD
    borderline_low: float = BORDERLINE_LOW
    rejection_threshold: float = REJECTION_THRESHOLD

    def __post_init__(self) -> None:
        if not (0.0 <= self.rejection_threshold <= 1.0):
            raise ValueError(
                f"rejection_threshold must be in [0.0, 1.0], got {self.rejection_threshold}"
            )
        if not (self.rejection_threshold <= self.borderline_low <= self.high_confidence_threshold):
            raise ValueError(
                f"thresholds must satisfy rejection <= borderline_low <= "
                f"high_confidence, got {self.rejection_threshold}, "
                f"{self.borderline_low}, {self.high_confidence_threshold}"
            )


@dataclass(frozen=True, slots=True)
class PromotionDecision:
    """A single promotion/demotion decision for one Signal.

    `original` is the input Signal; `target` is the proposed next state.
    If `target == original.status`, no transition is needed (the decision
    is informational). `reason` explains the rule that fired.
    """

    original: Signal
    target: SignalStatus
    reason: str

    @property
    def should_transition(self) -> bool:
        return self.target != self.original.status


class SignalPromoter:
    """Applies promotion/demotion rules to a batch of Signals.

    Pure: returns decisions only; does not mutate Signals or write to any
    Store. Callers translate decisions into lifecycle method calls
    (`signal.activate()`, `signal.hold()`, `signal.decay()`, `signal.reject()`)
    and persist via `persistence.lifecycle` helpers.
    """

    def __init__(self, policy: PromotionPolicy | None = None) -> None:
        self._policy = policy or PromotionPolicy()

    @property
    def policy(self) -> PromotionPolicy:
        return self._policy

    def evaluate(self, signal: Signal) -> PromotionDecision:
        """Decide the target state for one Signal.

        Rules (applied in order):
            1. DRAFT: never transitioned by the promoter. Drafts are
               runtime-internal (INV-8).
            2. VERIFIED with composite >= high_confidence: ACTIVE.
            3. VERIFIED with borderline_low <= composite < high_confidence: HELD.
            4. VERIFIED with composite < borderline_low: REJECTED.
            5. ACTIVE with composite < borderline_low: DECAYED.
               (The SIGNAL_LIFECYCLE graph allows ACTIVE -> {DECAYED,
               SUPERSEDED}; there is no ACTIVE -> HELD path. Borderline
               ACTIVE signals therefore decay.)
            6. ACTIVE otherwise: no change.
            7. HELD: no change (curator decides; deferred to next checkpoint).
            8. Terminal states (REJECTED, DECAYED, SUPERSEDED): no change.
        """
        current = signal.status

        if current == SignalStatus.DRAFT:
            return PromotionDecision(
                original=signal,
                target=current,
                reason="draft; promoter does not handle drafts",
            )

        if current == SignalStatus.HELD:
            return PromotionDecision(
                original=signal,
                target=current,
                reason="held; awaiting curator",
            )

        if current in {SignalStatus.REJECTED, SignalStatus.DECAYED, SignalStatus.SUPERSEDED}:
            return PromotionDecision(
                original=signal,
                target=current,
                reason=f"terminal state {current.value}; no transition",
            )

        composite = signal.score.composite

        if current == SignalStatus.VERIFIED:
            if composite >= self._policy.high_confidence_threshold:
                return PromotionDecision(
                    original=signal,
                    target=SignalStatus.ACTIVE,
                    reason=(
                        f"verified->active (composite={composite:.4f} >= "
                        f"{self._policy.high_confidence_threshold})"
                    ),
                )
            if composite >= self._policy.borderline_low:
                return PromotionDecision(
                    original=signal,
                    target=SignalStatus.HELD,
                    reason=(
                        f"verified->held (composite={composite:.4f} in borderline "
                        f"[{self._policy.borderline_low}, {self._policy.high_confidence_threshold}))"
                    ),
                )
            return PromotionDecision(
                original=signal,
                target=SignalStatus.REJECTED,
                reason=(
                    f"verified->rejected (composite={composite:.4f} < "
                    f"{self._policy.borderline_low})"
                ),
            )

        if current == SignalStatus.ACTIVE:
            if composite < self._policy.borderline_low:
                return PromotionDecision(
                    original=signal,
                    target=SignalStatus.DECAYED,
                    reason=(
                        f"active->decayed (composite={composite:.4f} < "
                        f"{self._policy.borderline_low}); ACTIVE cannot transition to HELD "
                        f"per SIGNAL_LIFECYCLE"
                    ),
                )
            return PromotionDecision(
                original=signal,
                target=current,
                reason=f"active retained (composite={composite:.4f})",
            )

        # Defensive: unhandled state.
        return PromotionDecision(
            original=signal,
            target=current,
            reason=f"unhandled state {current.value}",
        )

    def evaluate_many(self, signals: Iterable[Signal]) -> tuple[PromotionDecision, ...]:
        """Evaluate a batch of Signals."""
        return tuple(self.evaluate(s) for s in signals)


__all__ = [
    "PromotionDecision",
    "PromotionPolicy",
    "SignalPromoter",
    "HIGH_CONFIDENCE_THRESHOLD",
    "BORDERLINE_LOW",
    "REJECTION_THRESHOLD",
]