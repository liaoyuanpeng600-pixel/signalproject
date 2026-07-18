"""Tests for workflow.update_rules (Rules 1-4)."""

import pytest

from src.core.invariants import Score
from src.core.lifecycle import LifecycleError
from src.core.research import Research, ResearchStatus
from src.core.signals import (
    EntityRef,
    Signal,
    SignalDirection,
    SignalHorizon,
    SignalStatus,
)
from src.core.theses import Thesis, ThesisStatus
from src.workflow.update_rules import (
    ThesisUpdatePath,
    apply_thesis_update,
    decide_thesis_update_path,
    handle_new_signal,
    is_thesis_pending,
    is_thesis_ready_for_integration,
    resolve_conflicting_research,
)


def make_research() -> Research:
    return Research.create(
        entity_ref=EntityRef(id="entity-1", kind="company"),
        question="Is ACME undervalued?",
        signal_ids=("sig-1",),
    )


def make_thesis(interpretation: str = "ACME is undervalued.") -> Thesis:
    return Thesis.create(
        entity_ref=EntityRef(id="entity-1", kind="company"),
        interpretation=interpretation,
    )


def make_signal(claim: str = "ACME reported EPS of $1.20.") -> Signal:
    return Signal.create(
        entity_ref=EntityRef(id="entity-1", kind="company"),
        type="earnings",
        claim=claim,
        evidence_ids=("ev-1",),
        direction=SignalDirection.BULLISH,
        horizon=SignalHorizon.SHORT,
        score=Score(0.7, 0.9, 0.8, 0.6, 0.75),
        status=SignalStatus.DRAFT,
    )


# ===========================================================================
# Rule 1: New Signal Handling
# ===========================================================================


class TestHandleNewSignal:
    def test_advances_draft_to_verified(self) -> None:
        signal = make_signal()
        result = handle_new_signal(signal)
        assert result.accepted
        assert result.signal.status == SignalStatus.VERIFIED

    def test_rejects_non_draft_signal(self) -> None:
        signal = make_signal()
        verified = signal.verify()  # Already verified
        result = handle_new_signal(verified)
        assert not result.accepted
        assert "not DRAFT" in result.rationale

    def test_preserves_signal_attributes(self) -> None:
        signal = make_signal()
        original_id = signal.id
        result = handle_new_signal(signal)
        assert result.signal.id == original_id
        assert result.signal.claim == signal.claim
        assert result.signal.evidence_ids == signal.evidence_ids


# ===========================================================================
# Rule 2: Thesis Update Path Decision
# ===========================================================================


class TestDecideThesisUpdatePath:
    def test_no_existing_returns_evolve(self) -> None:
        decision = decide_thesis_update_path(make_research(), None)
        assert decision.path == ThesisUpdatePath.EVOLVE
        assert "no existing" in decision.rationale

    def test_same_content_returns_evolve(self) -> None:
        research = make_research()
        existing = make_thesis()
        # Both have the same entity_ref; "different" content
        decision = decide_thesis_update_path(research, existing)
        assert decision.path == ThesisUpdatePath.EVOLVE

    def test_aligning_content_returns_evolve(self) -> None:
        research = make_research()
        existing = make_thesis("Same conclusion.")
        decision = decide_thesis_update_path(research, existing)
        assert decision.path == ThesisUpdatePath.EVOLVE


class TestApplyThesisUpdate:
    def test_evolve_creates_evolved_thesis(self) -> None:
        research = make_research()
        existing = make_thesis()
        decision = decide_thesis_update_path(research, existing)
        updated = apply_thesis_update(
            decision, research, existing, "New interpretation", by="research-1"
        )
        assert updated.interpretation == "New interpretation"
        assert len(updated.evolution_history) == 1
        assert updated.evolution_history[0].new_interpretation == "New interpretation"

    def test_supersede_creates_new_thesis(self) -> None:
        from src.workflow.update_rules import ThesisUpdatePath

        research = make_research()
        existing = make_thesis()
        new = apply_thesis_update(
            decision=type("D", (), {"path": ThesisUpdatePath.SUPERSEDE})(),
            research=research,
            existing=existing,
            new_interpretation="Replacement interpretation",
            by="research-1",
        )
        # New Thesis has different ID
        assert new.id != existing.id
        # New Thesis records the supersession
        assert len(new.evolution_history) == 1
        assert new.evolution_history[0].kind == "supersede"

    def test_hold_returns_existing_with_open_question(self) -> None:
        from src.workflow.update_rules import ThesisUpdatePath

        research = make_research()
        existing = make_thesis()
        updated = apply_thesis_update(
            decision=type("D", (), {"path": ThesisUpdatePath.HOLD})(),
            research=research,
            existing=existing,
            new_interpretation="Doesn't matter",
            by="research-1",
        )
        # Same Thesis ID (existing is preserved)
        assert updated.id == existing.id
        # Open question is added
        assert len(updated.open_questions) >= 1

    def test_no_existing_creates_new(self) -> None:
        research = make_research()
        new = apply_thesis_update(
            decision=type("D", (), {"path": ThesisUpdatePath.EVOLVE})(),
            research=research,
            existing=None,
            new_interpretation="Fresh interpretation",
            by="research-1",
        )
        assert new.interpretation == "Fresh interpretation"
        assert new.entity_ref.id == "entity-1"


# ===========================================================================
# Rule 3: Conflicting Research
# ===========================================================================


class TestResolveConflictingResearch:
    def test_different_entities_no_conflict(self) -> None:
        a = Research.create(
            entity_ref=EntityRef(id="entity-1", kind="company"),
            question="Q1?",
            signal_ids=("sig-1",),
        )
        b = Research.create(
            entity_ref=EntityRef(id="entity-2", kind="company"),
            question="Q2?",
            signal_ids=("sig-2",),
        )
        result = resolve_conflicting_research(a, b)
        assert result.can_coexist
        assert "different entities" in result.rationale

    def test_same_entity_both_retained(self) -> None:
        a = Research.create(
            entity_ref=EntityRef(id="entity-1", kind="company"),
            question="Q1?",
            signal_ids=("sig-1",),
        )
        b = Research.create(
            entity_ref=EntityRef(id="entity-1", kind="company"),
            question="Q2 (different conclusion)?",
            signal_ids=("sig-2",),
        )
        result = resolve_conflicting_research(a, b)
        assert result.can_coexist
        assert "both retained" in result.rationale


# ===========================================================================
# Rule 4: Knowledge Accumulation
# ===========================================================================


class TestIsThesisReadyForIntegration:
    def test_evolving_is_ready(self) -> None:
        thesis = Thesis.create(
            entity_ref=EntityRef(id="entity-1", kind="company"),
            interpretation="ACME is undervalued based on peer multiples.",
            status=ThesisStatus.EVOLVING,
        )
        assert is_thesis_ready_for_integration(thesis) is True

    def test_mature_is_ready(self) -> None:
        thesis = Thesis.create(
            entity_ref=EntityRef(id="entity-1", kind="company"),
            interpretation="ACME is undervalued based on peer multiples.",
            status=ThesisStatus.MATURE,
        )
        assert is_thesis_ready_for_integration(thesis) is True

    def test_emerging_is_not_ready(self) -> None:
        thesis = Thesis.create(
            entity_ref=EntityRef(id="entity-1", kind="company"),
            interpretation="ACME is undervalued based on peer multiples.",
            status=ThesisStatus.EMERGING,
        )
        assert is_thesis_ready_for_integration(thesis) is False


class TestIsThesisPending:
    def test_emerging_is_pending(self) -> None:
        thesis = Thesis.create(
            entity_ref=EntityRef(id="entity-1", kind="company"),
            interpretation="ACME is undervalued based on peer multiples.",
            status=ThesisStatus.EMERGING,
        )
        assert is_thesis_pending(thesis) is True

    def test_evolving_is_not_pending(self) -> None:
        thesis = Thesis.create(
            entity_ref=EntityRef(id="entity-1", kind="company"),
            interpretation="ACME is undervalued based on peer multiples.",
            status=ThesisStatus.EVOLVING,
        )
        assert is_thesis_pending(thesis) is False