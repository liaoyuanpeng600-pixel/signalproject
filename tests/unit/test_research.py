"""Tests for the Research type."""

import pytest

from src.core.lifecycle import LifecycleError
from src.core.research import (
    CausalLink,
    Durability,
    PrecedentRef,
    Reasoning,
    Research,
    ResearchStatus,
    Reversibility,
)
from src.core.signals import EntityRef, SignalDirection, SignalHorizon


def make_research(status: ResearchStatus = ResearchStatus.OPEN) -> Research:
    return Research.create(
        entity_ref=EntityRef(id="entity-1", kind="company"),
        question="Is ACME undervalued?",
        signal_ids=("sig-1", "sig-2"),
    )


class TestResearchCreate:
    def test_minimal_creation(self) -> None:
        research = make_research()
        assert research.id
        assert research.entity_ref.id == "entity-1"
        assert research.question == "Is ACME undervalued?"
        assert research.status == ResearchStatus.OPEN
        assert research.concluded_at is None

    def test_with_reasoning(self) -> None:
        research = make_research()
        reasoning = Reasoning(
            significance=0.85,
            causality=(),
            durability=Durability.STRUCTURAL,
            reversibility=Reversibility.HARD,
            one_liner="ACME undervalued based on peer multiples.",
        )
        attached = research.attach_reasoning(reasoning)
        assert attached.reasoning is not None
        assert attached.reasoning.significance == 0.85


class TestResearchValidation:
    def test_empty_question_rejected(self) -> None:
        with pytest.raises(ValueError):
            Research.create(
                entity_ref=EntityRef(id="e", kind="company"),
                question="",
                signal_ids=("s1",),
            )

    def test_no_signals_rejected(self) -> None:
        with pytest.raises(ValueError, match="at least one Signal"):
            Research.create(
                entity_ref=EntityRef(id="e", kind="company"),
                question="Q?",
                signal_ids=(),
            )


class TestResearchLifecycle:
    def test_open_to_ongoing(self) -> None:
        r = make_research()
        ongoing = r.start()
        assert ongoing.status == ResearchStatus.ONGOING

    def test_open_to_concluded_direct(self) -> None:
        r = make_research()
        concluded = r.conclude()
        assert concluded.status == ResearchStatus.CONCLUDED
        assert concluded.concluded_at is not None

    def test_ongoing_to_concluded(self) -> None:
        r = make_research(ResearchStatus.ONGOING)
        concluded = r.conclude()
        assert concluded.status == ResearchStatus.CONCLUDED

    def test_open_to_paused_to_ongoing(self) -> None:
        r = make_research()
        paused = r.pause("Waiting for more signals")
        assert paused.status == ResearchStatus.PAUSED
        assert paused.held_reason == "Waiting for more signals"
        resumed = paused.resume()
        assert resumed.status == ResearchStatus.ONGOING

    def test_resume_from_non_paused_fails(self) -> None:
        r = make_research()
        with pytest.raises(ValueError):
            r.resume()

    def test_conclude_idempotent(self) -> None:
        r = make_research()
        c1 = r.conclude()
        c2 = c1.conclude()
        assert c2.status == ResearchStatus.CONCLUDED
        # concluded_at should not change on second conclude
        assert c2.concluded_at == c1.concluded_at


class TestResearchSignals:
    def test_add_signals(self) -> None:
        r = make_research()
        r2 = r.add_signals(("sig-3", "sig-4"))
        assert "sig-3" in r2.signal_ids
        assert "sig-4" in r2.signal_ids

    def test_add_signals_deduplicates(self) -> None:
        r = make_research()  # Already has sig-1, sig-2
        r2 = r.add_signals(("sig-2", "sig-3"))
        assert "sig-2" in r2.signal_ids
        assert "sig-3" in r2.signal_ids
        # No duplicate
        assert r2.signal_ids.count("sig-2") == 1


class TestResearchImmutability:
    def test_id_immutable(self) -> None:
        r = make_research()
        with pytest.raises(Exception):
            r.id = "new_id"  # type: ignore[misc]


class TestCausalLinkValidation:
    def test_valid_causal_link(self) -> None:
        link = CausalLink(
            to_entity=EntityRef(id="e2", kind="company"),
            mechanism="ACME supplier to BETA; BETA revenue affected.",
            likelihood="high",
            time_horizon=SignalHorizon.SHORT,
        )
        assert link.mechanism

    def test_invalid_likelihood(self) -> None:
        with pytest.raises(ValueError, match="likelihood"):
            CausalLink(
                to_entity=EntityRef(id="e2", kind="company"),
                mechanism="X",
                likelihood="very-high",  # Invalid
                time_horizon=SignalHorizon.SHORT,
            )

    def test_too_long_mechanism(self) -> None:
        with pytest.raises(ValueError, match="mechanism exceeds"):
            CausalLink(
                to_entity=EntityRef(id="e2", kind="company"),
                mechanism="x" * 300,
                likelihood="high",
                time_horizon=SignalHorizon.SHORT,
            )


class TestPrecedentRefValidation:
    def test_valid_precedent(self) -> None:
        p = PrecedentRef(signal_id="sig-prior", similarity=0.8, outcome="5% appreciation")
        assert p.similarity == 0.8

    def test_invalid_similarity(self) -> None:
        with pytest.raises(ValueError):
            PrecedentRef(signal_id="sig-1", similarity=1.5, outcome="x")


class TestReasoningValidation:
    def test_too_long_one_liner(self) -> None:
        with pytest.raises(ValueError):
            Reasoning(
                significance=0.5,
                one_liner="x" * 141,
            )

    def test_invalid_significance(self) -> None:
        with pytest.raises(ValueError):
            Reasoning(significance=1.5)


class TestResearchTraceability:
    def test_flag_traceability_gaps(self) -> None:
        r = make_research()
        flagged = r.flag_traceability_gaps()
        assert flagged.traceability_gaps is True
