"""Tests for workflow stages.

Tests focus on orchestration behavior: gate evaluation, failure routing,
and Object lifecycle transitions. Each stage is tested independently.
"""

import pytest

from src.core.ids import new_id
from src.workflow.context import PipelineContext
from src.workflow.stages import (
    EvidenceProductionStage,
    KnowledgeUpdateStage,
    ResearchSynthesisStage,
    SignalExtractionStage,
    SourceObservationStage,
    ThesisUpdateStage,
)
from src.workflow.types import StageStatus


# ===========================================================================
# Stage 1 — Source Observation
# ===========================================================================


class TestSourceObservationStage:
    def test_no_observer_returns_advance(self) -> None:
        ctx = PipelineContext()
        stage = SourceObservationStage(observer=None)
        result = stage.execute(ctx)
        # No observer means no observation attempted → stage does not fail
        assert result.advanced
        # No candidates, no degraded sources
        assert ctx.candidates == []
        assert ctx.degraded_sources == []

    def test_emits_stage_started_and_completed(self) -> None:
        ctx = PipelineContext()
        stage = SourceObservationStage()
        stage.execute(ctx)
        events = [e for e in ctx.events if e.__class__.__name__ in ("StageStarted", "StageCompleted")]
        assert len(events) >= 2

    def test_with_mock_observer(self) -> None:
        from src.core.sources import Source, SourceStatus, SourceType
        from src.workflow.types import CandidateObservation

        class MockObserver:
            def __init__(self, candidates_to_return: list):
                self.candidates = candidates_to_return
                self.call_count = 0

            def observe(self, source: Source) -> list:
                self.call_count += 1
                return self.candidates

        source = Source.create(type=SourceType.NEWS_ARTICLE, url="https://x.com", name="X")
        ctx = PipelineContext(sources=[source])

        candidate = CandidateObservation(
            source_id=source.id,
            content="ACME content",
            source_timestamp="2026-07-18T10:00:00+00:00",
            retrieved_at="2026-07-18T11:00:00+00:00",
            url="https://x.com",
        )
        observer = MockObserver([candidate])
        stage = SourceObservationStage(observer=observer)  # type: ignore[arg-type]
        result = stage.execute(ctx)
        assert result.advanced
        assert observer.call_count == 1
        assert len(ctx.candidates) == 1

    def test_skips_deactivated_sources(self) -> None:
        from src.core.sources import Source, SourceType
        from src.workflow.types import CandidateObservation

        class MockObserver:
            def __init__(self):
                self.call_count = 0

            def observe(self, source: Source) -> list:
                self.call_count += 1
                return [
                    CandidateObservation(
                        source_id=source.id,
                        content="X",
                        source_timestamp="2026-07-18T10:00:00+00:00",
                        retrieved_at="2026-07-18T11:00:00+00:00",
                        url="https://x.com",
                    )
                ]

        source = Source.create(type=SourceType.NEWS_ARTICLE, url="https://x.com", name="X")
        # Deactivate the source
        source = source.deactivate()
        ctx = PipelineContext(sources=[source])

        observer = MockObserver()
        stage = SourceObservationStage(observer=observer)  # type: ignore[arg-type]
        stage.execute(ctx)
        assert observer.call_count == 0  # Skipped
        assert ctx.candidates == []


# ===========================================================================
# Stage 2 — Evidence Production
# ===========================================================================


class TestEvidenceProductionStage:
    def test_no_producer(self) -> None:
        ctx = PipelineContext()
        stage = EvidenceProductionStage(producer=None)
        result = stage.execute(ctx)
        assert result.advanced

    def test_with_mock_producer(self) -> None:
        from src.core.evidence import Evidence, Quality
        from src.core.sources import Source, SourceType
        from src.workflow.types import CandidateObservation

        class MockProducer:
            def produce(self, candidate: CandidateObservation, source: Source) -> Evidence:
                return Evidence.create(
                    source_ids=(candidate.source_id,),
                    content=candidate.content,
                    quality=Quality(0.9, 0.9, 0.9),
                )

        source = Source.create(type=SourceType.NEWS_ARTICLE, url="https://x.com", name="X")
        candidate = CandidateObservation(
            source_id=source.id,
            content="ACME content",
            source_timestamp="2026-07-18T10:00:00+00:00",
            retrieved_at="2026-07-18T11:00:00+00:00",
            url="https://x.com",
        )
        ctx = PipelineContext(sources=[source], candidates=[candidate])

        stage = EvidenceProductionStage(producer=MockProducer())  # type: ignore[arg-type]
        result = stage.execute(ctx)
        assert result.advanced
        assert len(ctx.evidences) == 1

    def test_removes_consumed_candidates(self) -> None:
        from src.core.evidence import Evidence, Quality
        from src.core.sources import Source, SourceType
        from src.workflow.types import CandidateObservation

        class MockProducer:
            def produce(self, candidate: CandidateObservation, source: Source) -> Evidence:
                return Evidence.create(
                    source_ids=(candidate.source_id,),
                    content=candidate.content,
                    quality=Quality(0.9, 0.9, 0.9),
                )

        source = Source.create(type=SourceType.NEWS_ARTICLE, url="https://x.com", name="X")
        candidate = CandidateObservation(
            source_id=source.id,
            content="X",
            source_timestamp="2026-07-18T10:00:00+00:00",
            retrieved_at="2026-07-18T11:00:00+00:00",
            url="https://x.com",
        )
        ctx = PipelineContext(sources=[source], candidates=[candidate])

        stage = EvidenceProductionStage(producer=MockProducer())  # type: ignore[arg-type]
        stage.execute(ctx)
        # Candidate consumed (removed from context)
        assert len(ctx.candidates) == 0
        assert len(ctx.evidences) == 1


# ===========================================================================
# Stage 3 — Signal Extraction
# ===========================================================================


class TestSignalExtractionStage:
    def test_no_extractor(self) -> None:
        ctx = PipelineContext()
        stage = SignalExtractionStage()
        result = stage.execute(ctx)
        assert result.advanced

    def test_with_mock_extractor(self) -> None:
        from src.core.entities import Entity, EntityKind
        from src.core.evidence import Evidence, Quality
        from src.core.invariants import Score
        from src.core.signals import (
            EntityRef,
            Signal,
            SignalDirection,
            SignalHorizon,
            SignalStatus,
        )
        from src.core.sources import Source, SourceType

        class MockExtractor:
            def extract(self, evidence, entity) -> list:
                return [
                    Signal.create(
                        entity_ref=EntityRef(id=entity.id, kind="company"),
                        type="earnings",
                        claim="ACME reported EPS of $1.20, beating consensus by 10%.",
                        evidence_ids=(evidence.id,),
                        direction=SignalDirection.BULLISH,
                        horizon=SignalHorizon.SHORT,
                        score=Score(0.7, 0.9, 0.8, 0.6, 0.75),
                        status=SignalStatus.DRAFT,
                    )
                ]

        source = Source.create(type=SourceType.NEWS_ARTICLE, url="https://x.com", name="X")
        entity = Entity.create(kind=EntityKind.COMPANY, name="ACME")
        evidence = Evidence.create(
            source_ids=(source.id,),
            content="ACME content",
            quality=Quality(0.9, 0.9, 0.9),
        )

        ctx = PipelineContext(
            sources=[source],
            entities=[entity],
            evidences=[evidence],
        )

        def resolver(ref: EntityRef) -> Entity | None:
            return entity

        stage = SignalExtractionStage(
            extractor=MockExtractor(),  # type: ignore[arg-type]
            entity_resolver=resolver,
        )
        result = stage.execute(ctx)
        assert result.advanced
        assert len(ctx.signals) == 1
        # Signal transitioned DRAFT -> VERIFIED
        from src.core.signals import SignalStatus

        assert ctx.signals[0].status == SignalStatus.VERIFIED

    def test_unresolvable_entity_routes_to_failure(self) -> None:
        from src.core.entities import Entity, EntityKind
        from src.core.evidence import Evidence, Quality
        from src.core.signals import (
            EntityRef,
            Signal,
            SignalDirection,
            SignalHorizon,
            SignalStatus,
        )
        from src.core.sources import Source, SourceType

        class MockExtractor:
            def extract(self, evidence, entity) -> list:
                return [
                    Signal.create(
                        entity_ref=EntityRef(id=entity.id, kind="company"),
                        type="earnings",
                        claim="ACME reported EPS of $1.20, beating consensus by 10%.",
                        evidence_ids=(evidence.id,),
                        direction=SignalDirection.BULLISH,
                        horizon=SignalHorizon.SHORT,
                        score=Score(0.7, 0.9, 0.8, 0.6, 0.75),
                        status=SignalStatus.DRAFT,
                    )
                ]

        source = Source.create(type=SourceType.NEWS_ARTICLE, url="https://x.com", name="X")
        evidence = Evidence.create(
            source_ids=(source.id,),
            content="ACME content",
            quality=Quality(0.9, 0.9, 0.9),
        )
        ctx = PipelineContext(sources=[source], evidences=[evidence])

        def resolver(ref: EntityRef) -> Entity | None:
            return None  # Cannot resolve

        stage = SignalExtractionStage(
            extractor=MockExtractor(),  # type: ignore[arg-type]
            entity_resolver=resolver,
        )
        result = stage.execute(ctx)
        # Pipeline continues; failure is routed
        assert ctx.signals == []  # No signals verified

    def test_vague_claim_rejected(self) -> None:
        from src.core.entities import Entity, EntityKind
        from src.core.evidence import Evidence, Quality
        from src.core.invariants import Score
        from src.core.signals import (
            EntityRef,
            Signal,
            SignalDirection,
            SignalHorizon,
            SignalStatus,
        )
        from src.core.sources import Source, SourceType

        class MockExtractor:
            def extract(self, evidence, entity) -> list:
                return [
                    Signal.create(
                        entity_ref=EntityRef(id=entity.id, kind="company"),
                        type="earnings",
                        claim="maybe",  # too vague
                        evidence_ids=(evidence.id,),
                        direction=SignalDirection.BULLISH,
                        horizon=SignalHorizon.SHORT,
                        score=Score(0.7, 0.9, 0.8, 0.6, 0.75),
                        status=SignalStatus.DRAFT,
                    )
                ]

        source = Source.create(type=SourceType.NEWS_ARTICLE, url="https://x.com", name="X")
        entity = Entity.create(kind=EntityKind.COMPANY, name="ACME")
        evidence = Evidence.create(
            source_ids=(source.id,),
            content="X",
            quality=Quality(0.9, 0.9, 0.9),
        )
        ctx = PipelineContext(sources=[source], entities=[entity], evidences=[evidence])

        def resolver(ref: EntityRef) -> Entity | None:
            return entity

        stage = SignalExtractionStage(
            extractor=MockExtractor(),  # type: ignore[arg-type]
            entity_resolver=resolver,
        )
        stage.execute(ctx)
        assert len(ctx.signals) == 0
        assert len(ctx.rejected_signal_drafts) == 1


# ===========================================================================
# Stage 4 — Research Synthesis
# ===========================================================================


class TestResearchSynthesisStage:
    def test_no_synthesizer(self) -> None:
        ctx = PipelineContext()
        stage = ResearchSynthesisStage()
        result = stage.execute(ctx)
        assert result.advanced

    def test_with_mock_synthesizer(self) -> None:
        from src.core.entities import Entity, EntityKind
        from src.core.invariants import Score
        from src.core.research import Research
        from src.core.signals import (
            EntityRef,
            Signal,
            SignalDirection,
            SignalHorizon,
            SignalStatus,
        )

        class MockSynthesizer:
            def synthesize(self, signals, entity, question):
                return Research.create(
                    entity_ref=EntityRef(id=entity.id, kind="company"),
                    question=question,
                    signal_ids=tuple(s.id for s in signals),
                )

        entity = Entity.create(kind=EntityKind.COMPANY, name="ACME")
        # Signal must reference the actual entity id
        sig = Signal.create(
            entity_ref=EntityRef(id=entity.id, kind="company"),
            type="earnings",
            claim="ACME reported EPS of $1.20, beating consensus by 10%.",
            evidence_ids=("ev-1",),
            direction=SignalDirection.BULLISH,
            horizon=SignalHorizon.SHORT,
            score=Score(0.7, 0.9, 0.8, 0.6, 0.75),
            status=SignalStatus.ACTIVE,
        )
        ctx = PipelineContext(entities=[entity], signals=[sig])

        stage = ResearchSynthesisStage(synthesizer=MockSynthesizer())  # type: ignore[arg-type]
        result = stage.execute(ctx)
        assert result.advanced
        assert len(ctx.research_list) == 1


# ===========================================================================
# Stage 5 — Thesis Update
# ===========================================================================


class TestThesisUpdateStage:
    def test_no_crystallizer(self) -> None:
        ctx = PipelineContext()
        stage = ThesisUpdateStage()
        result = stage.execute(ctx)
        assert result.advanced

    def test_with_mock_crystallizer(self) -> None:
        from src.core.entities import Entity, EntityKind
        from src.core.research import Research
        from src.core.signals import EntityRef
        from src.core.theses import Thesis, ThesisStatus

        class MockCrystallizer:
            def crystallize(self, research: Research, prior: Thesis | None) -> Thesis:
                return Thesis.create(
                    entity_ref=research.entity_ref,
                    interpretation="ACME undervalued based on multiple data points.",
                    supporting_research_ids=(research.id,),
                    status=ThesisStatus.EMERGING,
                )

        entity = Entity.create(kind=EntityKind.COMPANY, name="ACME")
        # Research must reference the actual entity id
        research = Research.create(
            entity_ref=EntityRef(id=entity.id, kind="company"),
            question="Is ACME undervalued?",
            signal_ids=("sig-1",),
        )
        ctx = PipelineContext(entities=[entity], research_list=[research])

        stage = ThesisUpdateStage(crystallizer=MockCrystallizer())  # type: ignore[arg-type]
        result = stage.execute(ctx)
        assert result.advanced
        assert len(ctx.theses) == 1


# ===========================================================================
# Stage 6 — Knowledge Update
# ===========================================================================


class TestKnowledgeUpdateStage:
    def test_no_integrator(self) -> None:
        from src.core.signals import EntityRef
        from src.core.theses import Thesis, ThesisStatus

        ctx = PipelineContext()
        thesis = Thesis.create(
            entity_ref=EntityRef(id="entity-1", kind="company"),
            interpretation="ACME is undervalued based on peer multiples.",
            status=ThesisStatus.EVOLVING,
        )
        ctx.theses.append(thesis)
        stage = KnowledgeUpdateStage()
        result = stage.execute(ctx)
        assert result.advanced

    def test_emerging_thesis_routed_to_pending(self) -> None:
        from src.core.signals import EntityRef
        from src.core.theses import Thesis, ThesisStatus

        ctx = PipelineContext()
        thesis = Thesis.create(
            entity_ref=EntityRef(id="entity-1", kind="company"),
            interpretation="ACME is undervalued based on peer multiples.",
            status=ThesisStatus.EMERGING,
        )
        ctx.theses.append(thesis)
        stage = KnowledgeUpdateStage()
        stage.execute(ctx)
        # Moved to pending
        assert thesis not in ctx.theses
        assert thesis in ctx.theses_pending

    def test_evolving_thesis_integrated(self) -> None:
        from src.core.signals import EntityRef
        from src.core.theses import Thesis, ThesisStatus

        class MockIntegrator:
            def __init__(self):
                self.integrated = []

            def integrate(self, thesis):
                self.integrated.append(thesis)

        ctx = PipelineContext()
        thesis = Thesis.create(
            entity_ref=EntityRef(id="entity-1", kind="company"),
            interpretation="ACME is undervalued based on peer multiples.",
            status=ThesisStatus.EVOLVING,
        )
        ctx.theses.append(thesis)

        integrator = MockIntegrator()
        stage = KnowledgeUpdateStage(integrator=integrator)  # type: ignore[arg-type]
        stage.execute(ctx)
        assert len(integrator.integrated) == 1
        # Thesis is not in pending (it was integrated)
        assert thesis not in ctx.theses_pending


# ===========================================================================
# Default Stage List
# ===========================================================================


class TestDefaultStages:
    def test_six_stages(self) -> None:
        from src.workflow.stages import default_stages

        stages = default_stages()
        assert len(stages) == 6

    def test_stage_names(self) -> None:
        from src.workflow.stages import default_stages

        stages = default_stages()
        names = [s.name for s in stages]
        assert names == ["S1", "S2", "S3", "S4", "S5", "S6"]

    def test_stages_are_distinct_instances(self) -> None:
        from src.workflow.stages import default_stages

        stages = default_stages()
        ids = {id(s) for s in stages}
        assert len(ids) == 6  # All different instances