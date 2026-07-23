"""Tests for ResearchSynthesizer (Phase 5 Checkpoint 1)."""

import pytest

from src.core.entities import Entity, EntityKind
from src.core.ids import ID
from src.core.invariants import Score
from src.core.lifecycle import ResearchStatus
from src.core.research import Research
from src.core.signals import EntityRef, Signal, SignalDirection, SignalHorizon, SignalStatus
from src.research.synthesis import (
    ResearchSynthesizer,
    default_synthesis_key,
)


def _entity(name: str) -> Entity:
    return Entity.create(kind=EntityKind.COMPANY, name=name)


def _score(value: float) -> Score:
    return Score(
        magnitude=value,
        confidence=value,
        timeliness=value,
        novelty=value,
        actionability=value,
    )


def _signal(entity_id: str, signal_id: str, *, composite: float = 0.7) -> Signal:
    return Signal.create(
        entity_ref=EntityRef(id=entity_id, kind="company"),
        type="capital_action",
        claim=f"Signal {signal_id} claim",
        evidence_ids=(ID(f"ev-{signal_id}"),),
        direction=SignalDirection.BULLISH,
        horizon=SignalHorizon.SHORT,
        score=_score(composite),
        status=SignalStatus.ACTIVE,
    )


# ----------------------- default key -----------------------


class TestDefaultKey:
    def test_key_is_entity_id(self) -> None:
        sig = _signal("e-1", "s-1")
        assert default_synthesis_key(sig) == ("e-1",)


# ----------------------- synthesis: empty inputs -----------------------


class TestEmptyInputs:
    def test_no_signals_returns_empty_report(self) -> None:
        syn = ResearchSynthesizer()
        report = syn.synthesize(signals=(), existing_research=())
        assert report.signals_seen == 0
        assert report.research_created == ()
        assert report.research_updated == ()
        assert report.by_entity == {}


# ----------------------- synthesis: new Research -----------------------


class TestNewResearch:
    def test_creates_research_when_none_exists(self) -> None:
        syn = ResearchSynthesizer()
        s1 = _signal("e-1", "s-1")
        s2 = _signal("e-1", "s-2")
        report = syn.synthesize(
            signals=(s1, s2),
            existing_research=(),
        )
        assert len(report.research_created) == 1
        assert report.research_updated == ()
        assert report.by_entity == {"e-1": 1}

    def test_groups_by_entity(self) -> None:
        syn = ResearchSynthesizer()
        sigs = (
            _signal("e-1", "s-1"),
            _signal("e-1", "s-2"),
            _signal("e-2", "s-3"),
        )
        report = syn.synthesize(signals=sigs, existing_research=())
        assert len(report.research_created) == 2
        assert report.by_entity == {"e-1": 1, "e-2": 1}

    def test_custom_synthesis_key_groups_by_type(self) -> None:
        """A custom key can split signals for the same entity into multiple research items."""
        syn = ResearchSynthesizer(
            synthesis_key=lambda s: (str(s.entity_ref.id), s.type)
        )
        sig_capital = Signal.create(
            entity_ref=EntityRef(id="e-1", kind="company"),
            type="capital_action",
            claim="capital claim",
            evidence_ids=(ID("ev-1"),),
            direction=SignalDirection.BULLISH,
            horizon=SignalHorizon.SHORT,
            score=_score(0.7),
            status=SignalStatus.ACTIVE,
        )
        sig_governance = Signal.create(
            entity_ref=EntityRef(id="e-1", kind="company"),
            type="governance_change",
            claim="gov claim",
            evidence_ids=(ID("ev-2"),),
            direction=SignalDirection.NEUTRAL,
            horizon=SignalHorizon.MEDIUM,
            score=_score(0.7),
            status=SignalStatus.ACTIVE,
        )
        report = syn.synthesize(
            signals=(sig_capital, sig_governance), existing_research=()
        )
        assert len(report.research_created) == 2
        assert report.by_entity == {"e-1": 2}


# ----------------------- synthesis: existing Research -----------------------


class TestExistingResearch:
    def test_appends_to_existing_research(self) -> None:
        syn = ResearchSynthesizer()
        existing = Research.create(
            entity_ref=EntityRef(id="e-1", kind="company"),
            question="Q?",
            signal_ids=(ID("s-old"),),
        )
        # Make it OPEN/ONGOING.
        existing = existing.start()
        sig = _signal("e-1", "s-new")
        report = syn.synthesize(signals=(sig,), existing_research=(existing,))
        assert report.research_created == ()
        assert report.research_updated == (existing.id,)

    def test_ignores_concluded_research(self) -> None:
        """Concluded Research is not a target for new signals."""
        syn = ResearchSynthesizer()
        concluded = Research.create(
            entity_ref=EntityRef(id="e-1", kind="company"),
            question="old Q",
            signal_ids=(ID("s-old"),),
        ).conclude()
        sig = _signal("e-1", "s-new")
        report = syn.synthesize(signals=(sig,), existing_research=(concluded,))
        # A new Research must be created.
        assert len(report.research_created) == 1
        assert report.research_updated == ()

    def test_appends_to_most_recent_of_multiple(self) -> None:
        """If multiple OPEN Research exist for one entity, attach to the
        most recent (largest opened_at)."""
        syn = ResearchSynthesizer()
        r1 = Research.create(
            entity_ref=EntityRef(id="e-1", kind="company"),
            question="older",
            signal_ids=(ID("s-1"),),
        )
        r1 = r1.start()
        # Manually update opened_at to make r2 newer (dataclass is frozen).
        from dataclasses import replace as dc_replace

        r2_orig = Research.create(
            entity_ref=EntityRef(id="e-1", kind="company"),
            question="newer",
            signal_ids=(ID("s-2"),),
        )
        r2 = dc_replace(r2_orig, opened_at="2099-01-01T00:00:00Z").start()
        sig = _signal("e-1", "s-3")
        report = syn.synthesize(signals=(sig,), existing_research=(r1, r2))
        assert r2.id in report.research_updated
        assert r1.id not in report.research_updated