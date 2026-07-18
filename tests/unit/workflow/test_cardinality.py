"""Tests for workflow.cardinality."""

import pytest

from src.core.evidence import Evidence, Quality
from src.core.ids import new_id
from src.workflow.cardinality import (
    stage1_cardinality,
    stage2_cardinality,
    stage3_cardinality,
    stage4_cardinality,
    stage5_cardinality,
    stage6_cardinality,
)
from src.workflow.context import PipelineContext
from src.workflow.types import CandidateObservation


def make_candidate(source_id) -> CandidateObservation:
    return CandidateObservation(
        source_id=source_id,
        content="X",
        source_timestamp="2026-07-18T10:00:00+00:00",
        retrieved_at="2026-07-18T11:00:00+00:00",
        url="https://x.com",
    )


def make_evidence(source_id) -> Evidence:
    return Evidence.create(
        source_ids=(source_id,),
        content="X",
        quality=Quality(0.9, 0.9, 0.9),
    )


class TestStage1Cardinality:
    def test_empty_candidates_passes(self) -> None:
        ctx = PipelineContext()
        assert stage1_cardinality(ctx) is True

    def test_candidate_with_source_id_passes(self) -> None:
        ctx = PipelineContext()
        ctx.candidates.append(make_candidate(new_id()))
        assert stage1_cardinality(ctx) is True

    def test_candidate_without_source_id_fails(self) -> None:
        # Empty source_id is rejected at CandidateObservation construction.
        import pytest

        with pytest.raises(ValueError, match="source_id"):
            make_candidate("")


class TestStage2Cardinality:
    def test_zero_evidences_passes(self) -> None:
        assert stage2_cardinality([], []) is True

    def test_valid_ratio_passes(self) -> None:
        src = new_id()
        candidates = [make_candidate(src), make_candidate(src)]
        evidences = [make_evidence(src)]
        assert stage2_cardinality(candidates, evidences) is True

    def test_too_many_evidences_fails(self) -> None:
        src = new_id()
        candidates = [make_candidate(src)]
        evidences = [make_evidence(src), make_evidence(src)]
        assert stage2_cardinality(candidates, evidences) is False


class TestStage3Cardinality:
    def test_zero_signals_passes(self) -> None:
        assert stage3_cardinality([], []) is True

    def test_valid_ratio_passes(self) -> None:
        from src.core.invariants import Score
        from src.core.signals import (
            EntityRef,
            Signal,
            SignalDirection,
            SignalHorizon,
            SignalStatus,
        )

        ev = make_evidence(new_id())
        sig = Signal.create(
            entity_ref=EntityRef(id="e", kind="company"),
            type="earnings",
            claim="ACME reported EPS of $1.20.",
            evidence_ids=(ev.id,),
            direction=SignalDirection.BULLISH,
            horizon=SignalHorizon.SHORT,
            score=Score(0.7, 0.9, 0.8, 0.6, 0.75),
            status=SignalStatus.ACTIVE,
        )
        assert stage3_cardinality([ev], [sig]) is True


class TestStage4Cardinality:
    def test_empty_passes(self) -> None:
        assert stage4_cardinality([]) is True


class TestStage5Cardinality:
    def test_zero_research_zero_thesis_passes(self) -> None:
        assert stage5_cardinality(0, 0) is True

    def test_thesis_count_leq_research_count_passes(self) -> None:
        assert stage5_cardinality(5, 3) is True

    def test_thesis_count_0_passes(self) -> None:
        assert stage5_cardinality(0, 0) is True


class TestStage6Cardinality:
    def test_zero_passes(self) -> None:
        assert stage6_cardinality(0) is True