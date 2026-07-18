"""Tests for workflow.context."""

import pytest

from src.core.entities import Entity, EntityKind
from src.core.evidence import Evidence, Quality
from src.core.ids import ID, new_id
from src.core.invariants import Score
from src.core.research import Research
from src.core.signals import (
    EntityRef,
    Signal,
    SignalDirection,
    SignalHorizon,
    SignalStatus,
)
from src.core.sources import Source, SourceType
from src.core.theses import Thesis
from src.workflow.context import PipelineContext
from src.workflow.events import StageStarted
from src.workflow.types import CandidateObservation


def make_source() -> Source:
    return Source.create(type=SourceType.NEWS_ARTICLE, url="https://x.com", name="X")


def make_entity(name: str = "ACME") -> Entity:
    return Entity.create(kind=EntityKind.COMPANY, name=name)


def make_evidence(source_id: ID) -> Evidence:
    return Evidence.create(
        source_ids=(source_id,),
        content="ACME content.",
        quality=Quality(0.9, 0.9, 0.9),
    )


def make_signal(evidence_id: ID, status: SignalStatus = SignalStatus.ACTIVE) -> Signal:
    return Signal.create(
        entity_ref=EntityRef(id="entity-1", kind="company"),
        type="earnings",
        claim="ACME reported EPS of $1.20, beating consensus by 10%.",
        evidence_ids=(evidence_id,),
        direction=SignalDirection.BULLISH,
        horizon=SignalHorizon.SHORT,
        score=Score(0.7, 0.9, 0.8, 0.6, 0.75),
        status=status,
    )


def make_research() -> Research:
    return Research.create(
        entity_ref=EntityRef(id="entity-1", kind="company"),
        question="Is ACME undervalued?",
        signal_ids=("sig-1",),
    )


def make_thesis() -> Thesis:
    return Thesis.create(
        entity_ref=EntityRef(id="entity-1", kind="company"),
        interpretation="ACME is undervalued.",
    )


def make_candidate(source_id: ID) -> CandidateObservation:
    return CandidateObservation(
        source_id=source_id,
        content="ACME content.",
        source_timestamp="2026-07-18T10:00:00+00:00",
        retrieved_at="2026-07-18T11:00:00+00:00",
        url="https://x.com",
    )


class TestContextCreation:
    def test_default(self) -> None:
        ctx = PipelineContext()
        assert ctx.cycle_id  # auto-generated
        assert ctx.started_at
        assert ctx.sources == []
        assert ctx.entities == []
        assert ctx.candidates == []
        assert ctx.evidences == []
        assert ctx.signals == []
        assert ctx.research_list == []
        assert ctx.theses == []
        assert ctx.events == []

    def test_with_inputs(self) -> None:
        cycle_id = new_id()
        source = make_source()
        entity = make_entity()
        ctx = PipelineContext(cycle_id=cycle_id, sources=[source], entities=[entity])
        assert ctx.cycle_id == cycle_id
        assert len(ctx.sources) == 1
        assert len(ctx.entities) == 1


class TestContextEmit:
    def test_emit_appends_event(self) -> None:
        ctx = PipelineContext()
        event = StageStarted(cycle_id=ctx.cycle_id, stage_name="S1", started_at="t")
        ctx.emit(event)
        assert len(ctx.events) == 1
        assert ctx.events[0] is event


class TestContextStatistics:
    def test_signals_emitted_count(self) -> None:
        ctx = PipelineContext()
        ctx.signals.append(make_signal("ev-1"))
        ctx.signals.append(make_signal("ev-2"))
        assert ctx.signals_emitted == 2

    def test_research_emitted_count(self) -> None:
        ctx = PipelineContext()
        ctx.research_list.append(make_research())
        assert ctx.research_emitted == 1

    def test_theses_updated_count(self) -> None:
        ctx = PipelineContext()
        ctx.theses.append(make_thesis())
        assert ctx.theses_updated == 1

    def test_evidences_produced_count(self) -> None:
        ctx = PipelineContext()
        source = make_source()
        ev = make_evidence(source.id)
        ctx.evidences.append(ev)
        # Mark as non-retrievable
        non_ret = ev.mark_non_retrievable()
        ctx.non_retrievable_evidences.append(non_ret)
        assert ctx.evidences_produced == 2

    def test_empty_context_zero_counts(self) -> None:
        ctx = PipelineContext()
        assert ctx.signals_emitted == 0
        assert ctx.research_emitted == 0
        assert ctx.theses_updated == 0
        assert ctx.evidences_produced == 0


class TestContextContainers:
    def test_failure_destinations_distinct(self) -> None:
        ctx = PipelineContext()
        source = make_source()
        ev = make_evidence(source.id)
        ctx.evidences.append(ev)
        ctx.rejected_evidences.append(ev)
        assert len(ctx.evidences) == 1
        assert len(ctx.rejected_evidences) == 1

    def test_degraded_sources(self) -> None:
        ctx = PipelineContext()
        source = make_source()
        # Transition to DEACTIVATED
        deactivated = source.deactivate()
        ctx.degraded_sources.append(deactivated)
        assert len(ctx.degraded_sources) == 1
        assert ctx.degraded_sources[0].status.value == "deactivated"