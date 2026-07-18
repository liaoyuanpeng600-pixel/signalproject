"""Tests for workflow gates.

Covers all 23 gates organized by stage.
"""

from datetime import UTC, datetime, timedelta

import pytest

from src.core.ids import new_id
from src.workflow.context import PipelineContext
from src.workflow.gates import (
    S1G1SourceReachability,
    S1G2ContentRetrievability,
    S1G3TimestampPlausibility,
    S2G1SourceAttribution,
    S2G2ContentPreservation,
    S2G3QualityRecorded,
    S2G4Retrievability,
    S3G1EntityResolution,
    S3G2EvidenceGrounding,
    S3G3Falsifiability,
    S3G4DistinctEvent,
    S4G1QuestionCoherence,
    S4G2SufficientSignals,
    S4G3EntityContext,
    S4G4EvidenceTraceability,
    S5G1InterpretationCoherence,
    S5G2Falsifiability,
    S5G3EntityRecognition,
    S5G4ResearchGrounding,
    S6G1ThesisMaturity,
    S6G2TraceabilityPreservation,
    S6G3StructureConsistency,
    all_gates,
)
from src.workflow.types import CandidateObservation, FailurePath, GateResult


# ===========================================================================
# Stage 1 Gates
# ===========================================================================


class TestS1G1:
    def test_passes_with_candidates(self) -> None:
        ctx = PipelineContext()
        ctx.candidates.append(
            CandidateObservation(
                source_id=new_id(),
                content="X",
                source_timestamp="2026-07-18T10:00:00+00:00",
                retrieved_at="2026-07-18T11:00:00+00:00",
                url="https://x.com",
            )
        )
        result = S1G1SourceReachability().validate(ctx)
        assert result.passed

    def test_passes_with_no_sources(self) -> None:
        # No sources means no observation attempted → no failure.
        ctx = PipelineContext()
        result = S1G1SourceReachability().validate(ctx)
        assert result.passed

    def test_fails_when_sources_but_no_candidates(self) -> None:
        from src.core.sources import Source, SourceType

        ctx = PipelineContext()
        # Source exists but produced no candidates and no degraded
        source = Source.create(type=SourceType.NEWS_ARTICLE, url="https://x.com", name="X")
        ctx.sources.append(source)
        # No candidates, no degraded_sources
        result = S1G1SourceReachability().validate(ctx)
        assert not result.passed
        assert "no candidates" in result.reason

    def test_failure_path_degraded(self) -> None:
        assert S1G1SourceReachability().failure_path == FailurePath.DEGRADED

    def test_id(self) -> None:
        assert S1G1SourceReachability().id == "S1-G1"


class TestS1G2:
    def test_passes_with_valid_content(self) -> None:
        ctx = PipelineContext()
        ctx.candidates.append(
            CandidateObservation(
                source_id=new_id(),
                content="ACME content",
                source_timestamp="2026-07-18T10:00:00+00:00",
                retrieved_at="2026-07-18T11:00:00+00:00",
                url="https://x.com",
            )
        )
        result = S1G2ContentRetrievability().validate(ctx)
        assert result.passed

    def test_fails_with_empty_content(self) -> None:
        ctx = PipelineContext()
        ctx.candidates.append(
            CandidateObservation(
                source_id=new_id(),
                content="   ",  # whitespace only
                source_timestamp="2026-07-18T10:00:00+00:00",
                retrieved_at="2026-07-18T11:00:00+00:00",
                url="https://x.com",
            )
        )
        result = S1G2ContentRetrievability().validate(ctx)
        assert not result.passed

    def test_failure_path_degraded(self) -> None:
        assert S1G2ContentRetrievability().failure_path == FailurePath.DEGRADED


class TestS1G3:
    def test_passes_with_valid_timestamp(self) -> None:
        from datetime import UTC, datetime, timedelta

        ctx = PipelineContext()
        # Use a timestamp 1 hour ago (in the past, not in future, not too old)
        recent = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        ctx.candidates.append(
            CandidateObservation(
                source_id=new_id(),
                content="X",
                source_timestamp=recent,
                retrieved_at=recent,
                url="https://x.com",
            )
        )
        result = S1G3TimestampPlausibility().validate(ctx)
        assert result.passed

    def test_fails_with_future_timestamp(self) -> None:
        ctx = PipelineContext()
        future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
        ctx.candidates.append(
            CandidateObservation(
                source_id=new_id(),
                content="X",
                source_timestamp=future,
                retrieved_at=future,
                url="https://x.com",
            )
        )
        result = S1G3TimestampPlausibility().validate(ctx)
        assert not result.passed
        assert "future" in result.reason

    def test_fails_with_old_timestamp(self) -> None:
        ctx = PipelineContext()
        old = (datetime.now(UTC) - timedelta(days=60)).isoformat()
        ctx.candidates.append(
            CandidateObservation(
                source_id=new_id(),
                content="X",
                source_timestamp=old,
                retrieved_at="2026-07-18T11:00:00+00:00",
                url="https://x.com",
            )
        )
        result = S1G3TimestampPlausibility().validate(ctx)
        assert not result.passed
        assert "old" in result.reason

    def test_fails_with_invalid_format(self) -> None:
        ctx = PipelineContext()
        ctx.candidates.append(
            CandidateObservation(
                source_id=new_id(),
                content="X",
                source_timestamp="not-a-timestamp",
                retrieved_at="2026-07-18T11:00:00+00:00",
                url="https://x.com",
            )
        )
        result = S1G3TimestampPlausibility().validate(ctx)
        assert not result.passed

    def test_failure_path_flag(self) -> None:
        assert S1G3TimestampPlausibility().failure_path == FailurePath.FLAG


# ===========================================================================
# Stage 2 Gates
# ===========================================================================


def make_evidence(source_ids: tuple = ("src-1",)) -> object:
    from src.core.evidence import Evidence, Quality

    return Evidence.create(
        source_ids=source_ids,
        content="ACME content",
        quality=Quality(0.9, 0.9, 0.9),
    )


class TestS2G1:
    def test_passes_with_source(self) -> None:
        ctx = PipelineContext()
        ctx.evidences.append(make_evidence())
        result = S2G1SourceAttribution().validate(ctx)
        assert result.passed

    def test_failure_path_reject(self) -> None:
        assert S2G1SourceAttribution().failure_path == FailurePath.REJECT


class TestS2G2:
    def test_passes_with_content(self) -> None:
        ctx = PipelineContext()
        ctx.evidences.append(make_evidence())
        result = S2G2ContentPreservation().validate(ctx)
        assert result.passed


class TestS2G3:
    def test_passes_with_valid_quality(self) -> None:
        ctx = PipelineContext()
        ctx.evidences.append(make_evidence())
        result = S2G3QualityRecorded().validate(ctx)
        assert result.passed


class TestS2G4:
    def test_always_passes_at_gate_level(self) -> None:
        # S2-G4 is a routing gate; failure is captured separately.
        ctx = PipelineContext()
        ctx.evidences.append(make_evidence())
        result = S2G4Retrievability().validate(ctx)
        assert result.passed

    def test_marks_non_retrievable(self) -> None:
        from src.core.evidence import Evidence, Quality

        ctx = PipelineContext()
        ev = Evidence.create(
            source_ids=("src-1",),
            content="X",
            quality=Quality(0.9, 0.9, 0.9),
        )
        # Mark as non-retrievable
        non_ret = ev.mark_non_retrievable()
        ctx.evidences.append(non_ret)
        S2G4Retrievability().validate(ctx)
        # After validation, the non-retrievable evidence is moved out
        assert non_ret in ctx.non_retrievable_evidences
        assert non_ret not in ctx.evidences


# ===========================================================================
# Stage 3 Gates
# ===========================================================================


def make_signal(claim: str = "ACME reported EPS of $1.20, beating consensus by 10%.") -> object:
    from src.core.invariants import Score
    from src.core.signals import (
        EntityRef,
        Signal,
        SignalDirection,
        SignalHorizon,
        SignalStatus,
    )

    return Signal.create(
        entity_ref=EntityRef(id="entity-1", kind="company"),
        type="earnings",
        claim=claim,
        evidence_ids=("ev-1",),
        direction=SignalDirection.BULLISH,
        horizon=SignalHorizon.SHORT,
        score=Score(0.7, 0.9, 0.8, 0.6, 0.75),
        status=SignalStatus.ACTIVE,
    )


class TestS3G1:
    def test_passes_with_known_entity(self) -> None:
        from src.core.entities import Entity, EntityKind
        from src.core.signals import (
            EntityRef,
            Signal,
            SignalDirection,
            SignalHorizon,
            SignalStatus,
        )
        from src.core.invariants import Score

        ctx = PipelineContext()
        entity = Entity.create(kind=EntityKind.COMPANY, name="ACME")
        ctx.entities.append(entity)
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
        ctx.signals.append(sig)
        result = S3G1EntityResolution().validate(ctx)
        assert result.passed

    def test_fails_with_unknown_entity(self) -> None:
        ctx = PipelineContext()
        # No entities registered
        ctx.signals.append(make_signal())
        result = S3G1EntityResolution().validate(ctx)
        assert not result.passed

    def test_failure_path_reject(self) -> None:
        assert S3G1EntityResolution().failure_path == FailurePath.REJECT


class TestS3G2:
    def test_passes_with_evidence(self) -> None:
        ctx = PipelineContext()
        ctx.signals.append(make_signal())
        result = S3G2EvidenceGrounding().validate(ctx)
        assert result.passed

    def test_fails_without_evidence_raises_at_construction(self) -> None:
        # INV-1 prevents construction of signals with no evidence.
        # S3G2 is a defensive check (for backup).
        import pytest

        from src.core.signals import (
            EntityRef,
            Signal,
            SignalDirection,
            SignalHorizon,
            SignalStatus,
        )
        from src.core.invariants import Score

        with pytest.raises(ValueError, match="INV-1"):
            Signal.create(
                entity_ref=EntityRef(id="e", kind="company"),
                type="earnings",
                claim="X",
                evidence_ids=(),  # No evidence — INV-1 fails
                direction=SignalDirection.BULLISH,
                horizon=SignalHorizon.SHORT,
                score=Score(0.5, 0.5, 0.5, 0.5, 0.5),
                status=SignalStatus.ACTIVE,
            )

    def test_invariant_not_retryable(self) -> None:
        assert S3G2EvidenceGrounding().retryable is False


class TestS3G3:
    def test_passes_with_specific_claim(self) -> None:
        ctx = PipelineContext()
        ctx.signals.append(make_signal())
        result = S3G3Falsifiability().validate(ctx)
        assert result.passed

    def test_fails_with_vague_claim(self) -> None:
        ctx = PipelineContext()
        ctx.signals.append(make_signal(claim="X"))  # too short
        result = S3G3Falsifiability().validate(ctx)
        assert not result.passed


class TestS3G4:
    def test_passes_with_specific_event(self) -> None:
        ctx = PipelineContext()
        ctx.signals.append(make_signal())
        result = S3G4DistinctEvent().validate(ctx)
        assert result.passed

    def test_fails_with_vague_keyword(self) -> None:
        ctx = PipelineContext()
        ctx.signals.append(make_signal(claim="ACME maybe will do something general."))
        result = S3G4DistinctEvent().validate(ctx)
        assert not result.passed


# ===========================================================================
# Stage 4 Gates
# ===========================================================================


def make_research(question: str = "Is ACME undervalued?") -> object:
    from src.core.signals import EntityRef
    from src.core.research import Research

    return Research.create(
        entity_ref=EntityRef(id="entity-1", kind="company"),
        question=question,
        signal_ids=("sig-1",),
    )


class TestS4G1:
    def test_passes_with_question(self) -> None:
        ctx = PipelineContext()
        ctx.research_list.append(make_research())
        result = S4G1QuestionCoherence().validate(ctx)
        assert result.passed


class TestS4G2:
    def test_passes_with_signals(self) -> None:
        ctx = PipelineContext()
        ctx.research_list.append(make_research())
        result = S4G2SufficientSignals().validate(ctx)
        assert result.passed

    def test_fails_without_signals_raises_at_construction(self) -> None:
        # Research with no signals is rejected at construction.
        import pytest

        from src.core.signals import EntityRef
        from src.core.research import Research

        with pytest.raises(ValueError, match="at least one Signal"):
            Research.create(
                entity_ref=EntityRef(id="entity-1", kind="company"),
                question="Q?",
                signal_ids=(),  # No signals
            )


class TestS4G3:
    def test_passes_with_known_entity(self) -> None:
        from src.core.entities import Entity, EntityKind

        ctx = PipelineContext()
        entity = Entity.create(kind=EntityKind.COMPANY, name="ACME")
        ctx.entities.append(entity)
        # Research must reference the actual entity id
        from src.core.research import Research
        from src.core.signals import EntityRef

        research = Research.create(
            entity_ref=EntityRef(id=entity.id, kind="company"),
            question="Q?",
            signal_ids=("sig-1",),
        )
        ctx.research_list.append(research)
        result = S4G3EntityContext().validate(ctx)
        assert result.passed

    def test_fails_with_unknown_entity(self) -> None:
        ctx = PipelineContext()
        ctx.research_list.append(make_research())
        result = S4G3EntityContext().validate(ctx)
        assert not result.passed

    def test_failure_path_hold(self) -> None:
        assert S4G3EntityContext().failure_path == FailurePath.HOLD


class TestS4G4:
    def test_always_passes(self) -> None:
        # S4-G4 flags but doesn't block.
        ctx = PipelineContext()
        result = S4G4EvidenceTraceability().validate(ctx)
        assert result.passed


# ===========================================================================
# Stage 5 Gates
# ===========================================================================


def make_thesis(interpretation: str = "ACME is undervalued based on peer multiples.") -> object:
    from src.core.signals import EntityRef
    from src.core.theses import Thesis

    return Thesis.create(
        entity_ref=EntityRef(id="entity-1", kind="company"),
        interpretation=interpretation,
    )


class TestS5G1:
    def test_passes_with_interpretation(self) -> None:
        ctx = PipelineContext()
        ctx.theses.append(make_thesis())
        result = S5G1InterpretationCoherence().validate(ctx)
        assert result.passed


class TestS5G2:
    def test_passes_with_specific_interpretation(self) -> None:
        ctx = PipelineContext()
        ctx.theses.append(make_thesis())
        result = S5G2Falsifiability().validate(ctx)
        assert result.passed

    def test_fails_with_vague_interpretation(self) -> None:
        ctx = PipelineContext()
        ctx.theses.append(make_thesis("X"))  # too short
        result = S5G2Falsifiability().validate(ctx)
        assert not result.passed


class TestS5G3:
    def test_passes_with_known_entity(self) -> None:
        from src.core.entities import Entity, EntityKind
        from src.core.signals import EntityRef
        from src.core.theses import Thesis

        ctx = PipelineContext()
        entity = Entity.create(kind=EntityKind.COMPANY, name="ACME")
        ctx.entities.append(entity)
        # Thesis must reference the actual entity id
        thesis = Thesis.create(
            entity_ref=EntityRef(id=entity.id, kind="company"),
            interpretation="ACME is undervalued based on peer multiples.",
        )
        ctx.theses.append(thesis)
        result = S5G3EntityRecognition().validate(ctx)
        assert result.passed

    def test_fails_with_unknown_entity(self) -> None:
        ctx = PipelineContext()
        ctx.theses.append(make_thesis())
        result = S5G3EntityRecognition().validate(ctx)
        assert not result.passed

    def test_failure_path_hold(self) -> None:
        assert S5G3EntityRecognition().failure_path == FailurePath.HOLD


class TestS5G4:
    def test_passes_with_research(self) -> None:
        from src.core.signals import EntityRef
        from src.core.theses import Thesis

        ctx = PipelineContext()
        t = Thesis.create(
            entity_ref=EntityRef(id="entity-1", kind="company"),
            interpretation="X is undervalued based on peer multiples and growth.",
            supporting_research_ids=("research-1",),
        )
        ctx.theses.append(t)
        result = S5G4ResearchGrounding().validate(ctx)
        assert result.passed

    def test_invariant_not_retryable(self) -> None:
        assert S5G4ResearchGrounding().retryable is False


# ===========================================================================
# Stage 6 Gates
# ===========================================================================


def make_thesis_emerging() -> object:
    from src.core.signals import EntityRef
    from src.core.theses import Thesis, ThesisStatus

    return Thesis.create(
        entity_ref=EntityRef(id="entity-1", kind="company"),
        interpretation="ACME is undervalued based on peer multiples.",
        status=ThesisStatus.EMERGING,
    )


def make_thesis_evolving() -> object:
    from src.core.signals import EntityRef
    from src.core.theses import Thesis, ThesisStatus

    return Thesis.create(
        entity_ref=EntityRef(id="entity-1", kind="company"),
        interpretation="ACME is undervalued based on peer multiples.",
        status=ThesisStatus.EVOLVING,
    )


class TestS6G1:
    def test_passes_with_evolving(self) -> None:
        ctx = PipelineContext()
        ctx.theses.append(make_thesis_evolving())
        result = S6G1ThesisMaturity().validate(ctx)
        assert result.passed

    def test_fails_with_emerging(self) -> None:
        ctx = PipelineContext()
        ctx.theses.append(make_thesis_emerging())
        result = S6G1ThesisMaturity().validate(ctx)
        assert not result.passed

    def test_failure_path_pending(self) -> None:
        assert S6G1ThesisMaturity().failure_path == FailurePath.PENDING


class TestS6G2:
    def test_passes(self) -> None:
        ctx = PipelineContext()
        ctx.theses.append(make_thesis_evolving())
        result = S6G2TraceabilityPreservation().validate(ctx)
        assert result.passed

    def test_failure_path_pending(self) -> None:
        assert S6G2TraceabilityPreservation().failure_path == FailurePath.PENDING


class TestS6G3:
    def test_passes(self) -> None:
        ctx = PipelineContext()
        ctx.theses.append(make_thesis_evolving())
        result = S6G3StructureConsistency().validate(ctx)
        assert result.passed

    def test_failure_path_pending(self) -> None:
        assert S6G3StructureConsistency().failure_path == FailurePath.PENDING


# ===========================================================================
# Gate Registry
# ===========================================================================


class TestAllGates:
    def test_count(self) -> None:
        gates = all_gates()
        # 3 + 4 + 4 + 4 + 4 + 3 = 22 effective gates
        # (S3-G2 and S5-G4 are invariants; they are present in the registry)
        assert len(gates) == 22

    def test_unique_ids(self) -> None:
        gates = all_gates()
        ids = [g.id for g in gates]
        assert len(ids) == len(set(ids))

    def test_all_have_failure_paths(self) -> None:
        for gate in all_gates():
            assert gate.failure_path in {
                FailurePath.REJECT,
                FailurePath.HOLD,
                FailurePath.PENDING,
                FailurePath.DEGRADED,
                FailurePath.FLAG,
            }