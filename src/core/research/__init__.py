"""
Research type per Object Model §5.

Research is an organized investigation into an Entity, sector, or question.
It aggregates multiple Signals into a coherent intermediate understanding.
Research bridges observation (Signals) and interpretation (Thesis).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum

from src.core.ids import ID, new_id
from src.core.lifecycle import RESEARCH_LIFECYCLE, ResearchStatus, assert_transition
from src.core.signals import EntityRef, SignalDirection, SignalHorizon
from src.core.timestamps import now_utc


class Durability(str, Enum):
    """How long the effect of a Signal/Research is expected to persist."""

    TRANSIENT = "transient"  # <1 trading day
    SHORT = "short"  # 1–30 trading days
    STRUCTURAL = "structural"  # >30 trading days


class Reversibility(str, Enum):
    """How easily the change could be undone."""

    IRREVERSIBLE = "irreversible"
    HARD = "hard"
    EASY = "easy"


@dataclass(frozen=True, slots=True)
class CausalLink:
    """A causal relationship to another Entity."""

    to_entity: EntityRef
    mechanism: str  # ≤280 chars, concrete causal claim
    likelihood: str  # "low" | "medium" | "high"
    time_horizon: SignalHorizon

    def __post_init__(self) -> None:
        if not self.mechanism:
            raise ValueError("CausalLink.mechanism is required")
        if len(self.mechanism) > 280:
            raise ValueError(f"CausalLink.mechanism exceeds 280 chars: {len(self.mechanism)}")
        if self.likelihood not in {"low", "medium", "high"}:
            raise ValueError(f"CausalLink.likelihood must be one of low/medium/high, got {self.likelihood!r}")


@dataclass(frozen=True, slots=True)
class PrecedentRef:
    """A reference to a prior Signal with similar type/direction/entity."""

    signal_id: ID
    similarity: float  # 0.0–1.0
    outcome: str  # What actually happened, recorded post-hoc

    def __post_init__(self) -> None:
        if not self.signal_id:
            raise ValueError("PrecedentRef.signal_id is required")
        if not (0.0 <= self.similarity <= 1.0):
            raise ValueError(f"PrecedentRef.similarity must be in [0.0, 1.0], got {self.similarity}")


@dataclass(frozen=True, slots=True)
class Reasoning:
    """Structured output of the analyst agent (or equivalent)."""

    significance: float  # 0.0–1.0
    causality: tuple[CausalLink, ...] = ()
    durability: Durability = Durability.SHORT
    reversibility: Reversibility = Reversibility.EASY
    precedents: tuple[PrecedentRef, ...] = ()
    one_liner: str = ""  # ≤140 chars, for reports

    def __post_init__(self) -> None:
        if not (0.0 <= self.significance <= 1.0):
            raise ValueError(f"Reasoning.significance must be in [0.0, 1.0], got {self.significance}")
        if len(self.one_liner) > 140:
            raise ValueError(f"Reasoning.one_liner exceeds 140 chars: {len(self.one_liner)}")


@dataclass(frozen=True, slots=True)
class Research:
    """An organized investigation into an Entity, sector, or question.

    Research is the bridge between observation (Signals) and interpretation
    (Thesis). It is frozen: id is immutable. Status transitions are validated
    against RESEARCH_LIFECYCLE.
    """

    id: ID
    entity_ref: EntityRef
    question: str  # What this Research investigates
    signal_ids: tuple[ID, ...]  # Aggregated Signals
    status: ResearchStatus = ResearchStatus.OPEN
    opened_at: str = field(default_factory=now_utc)
    concluded_at: str | None = None
    reasoning: Reasoning | None = None  # Optional structured analysis
    traceability_gaps: bool = False  # Set if S4-G4 partially failed
    held_reason: str | None = None  # If status=paused or held

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("Research.id is required")
        if not self.question:
            raise ValueError("Research.question is required")
        if len(self.signal_ids) < 1:
            raise ValueError("Research must aggregate at least one Signal")
        if self.status == ResearchStatus.CONCLUDED and self.concluded_at is None:
            # Auto-stamp if concluded but no timestamp provided.
            object.__setattr__(self, "concluded_at", now_utc())

    def transition(self, new_status: ResearchStatus) -> "Research":
        """Transition to a new status. Validates against RESEARCH_LIFECYCLE.

        Raises:
            LifecycleError: If the transition is not allowed.
        """
        assert_transition(RESEARCH_LIFECYCLE, self.status, new_status)
        return replace(self, status=new_status)

    def start(self) -> "Research":
        """Begin active investigation."""
        return self.transition(ResearchStatus.ONGOING)

    def pause(self, reason: str | None = None) -> "Research":
        """Pause the investigation."""
        result = self.transition(ResearchStatus.PAUSED)
        if reason:
            result = replace(result, held_reason=reason)
        return result

    def resume(self) -> "Research":
        """Resume a paused investigation."""
        if self.status != ResearchStatus.PAUSED:
            raise ValueError(f"Cannot resume from {self.status}")
        return self.transition(ResearchStatus.ONGOING)

    def conclude(self) -> "Research":
        """Conclude the investigation. Terminal."""
        if self.status == ResearchStatus.CONCLUDED:
            return self
        new = self.transition(ResearchStatus.CONCLUDED)
        if new.concluded_at is None:
            new = replace(new, concluded_at=now_utc())
        return new

    def add_signals(self, signal_ids: tuple[ID, ...]) -> "Research":
        """Append additional Signals to this Research."""
        existing = set(self.signal_ids)
        new_ids = tuple(sid for sid in signal_ids if sid not in existing)
        return replace(self, signal_ids=self.signal_ids + new_ids)

    def attach_reasoning(self, reasoning: Reasoning) -> "Research":
        """Attach structured reasoning to this Research."""
        return replace(self, reasoning=reasoning)

    def flag_traceability_gaps(self) -> "Research":
        """Mark this Research as having traceability gaps (S4-G4)."""
        return replace(self, traceability_gaps=True)

    @classmethod
    def create(
        cls,
        entity_ref: EntityRef,
        question: str,
        signal_ids: tuple[ID, ...],
        id: ID | None = None,
        reasoning: Reasoning | None = None,
        held_reason: str | None = None,
    ) -> "Research":
        """Factory method to create new Research."""
        return cls(
            id=id if id is not None else new_id(),
            entity_ref=entity_ref,
            question=question,
            signal_ids=signal_ids,
            reasoning=reasoning,
            held_reason=held_reason,
        )
