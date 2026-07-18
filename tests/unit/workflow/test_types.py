"""Tests for workflow.types."""

import pytest

from src.workflow.types import (
    CandidateObservation,
    FailurePath,
    GateResult,
    StageResult,
    StageStatus,
)


class TestStageStatus:
    def test_advance(self) -> None:
        assert StageStatus.ADVANCE.value == "advance"

    def test_fail_variants(self) -> None:
        assert StageStatus.FAIL_REJECT.value == "fail_reject"
        assert StageStatus.FAIL_HOLD.value == "fail_hold"
        assert StageStatus.FAIL_PENDING.value == "fail_pending"
        assert StageStatus.FAIL_DEGRADED.value == "fail_degraded"
        assert StageStatus.FAIL_FLAG.value == "fail_flag"


class TestFailurePath:
    def test_all_paths(self) -> None:
        assert FailurePath.REJECT.value == "reject"
        assert FailurePath.HOLD.value == "hold"
        assert FailurePath.PENDING.value == "pending"
        assert FailurePath.DEGRADED.value == "degraded"
        assert FailurePath.FLAG.value == "flag"
        assert FailurePath.NONE.value == "none"


class TestGateResult:
    def test_pass(self) -> None:
        result = GateResult.pass_()
        assert result.passed is True
        assert result.reason is None

    def test_fail(self) -> None:
        result = GateResult.fail("some reason")
        assert result.passed is False
        assert result.reason == "some reason"

    def test_frozen(self) -> None:
        # GateResult is frozen dataclass — cannot mutate
        result = GateResult.pass_()
        with pytest.raises(Exception):  # FrozenInstanceError
            result.passed = False  # type: ignore[misc]


class TestStageResult:
    def test_default(self) -> None:
        result = StageResult(status=StageStatus.ADVANCE)
        assert result.status == StageStatus.ADVANCE
        assert result.failure_path == FailurePath.NONE
        assert result.failure_reason is None
        assert result.retryable is False
        assert result.output == {}

    def test_advanced_property(self) -> None:
        advance = StageResult(status=StageStatus.ADVANCE)
        fail = StageResult(status=StageStatus.FAIL_REJECT, failure_path=FailurePath.REJECT)
        assert advance.advanced is True
        assert fail.advanced is False

    def test_failed_property(self) -> None:
        advance = StageResult(status=StageStatus.ADVANCE)
        fail = StageResult(status=StageStatus.FAIL_DEGRADED, failure_path=FailurePath.DEGRADED)
        assert advance.failed is False
        assert fail.failed is True

    def test_with_output(self) -> None:
        result = StageResult(
            status=StageStatus.ADVANCE,
            output={"count": 5, "items": [1, 2, 3]},
        )
        assert result.output["count"] == 5
        assert result.output["items"] == [1, 2, 3]


class TestCandidateObservation:
    def test_minimal_creation(self) -> None:
        from src.core.ids import new_id

        source_id = new_id()
        candidate = CandidateObservation(
            source_id=source_id,
            content="ACME announced a buyback.",
            source_timestamp="2026-07-18T10:00:00+00:00",
            retrieved_at="2026-07-18T11:00:00+00:00",
            url="https://reuters.com/article/123",
        )
        assert candidate.source_id == source_id
        assert candidate.content == "ACME announced a buyback."
        assert candidate.url == "https://reuters.com/article/123"

    def test_frozen(self) -> None:
        from src.core.ids import new_id

        candidate = CandidateObservation(
            source_id=new_id(),
            content="X",
            source_timestamp="2026-07-18T10:00:00+00:00",
            retrieved_at="2026-07-18T11:00:00+00:00",
            url="https://x.com",
        )
        with pytest.raises(Exception):
            candidate.content = "Y"  # type: ignore[misc]

    def test_empty_content_rejected(self) -> None:
        from src.core.ids import new_id

        with pytest.raises(ValueError):
            CandidateObservation(
                source_id=new_id(),
                content="",
                source_timestamp="2026-07-18T10:00:00+00:00",
                retrieved_at="2026-07-18T11:00:00+00:00",
                url="https://x.com",
            )

    def test_empty_source_id_rejected(self) -> None:
        with pytest.raises(ValueError):
            CandidateObservation(
                source_id="",
                content="X",
                source_timestamp="2026-07-18T10:00:00+00:00",
                retrieved_at="2026-07-18T11:00:00+00:00",
                url="https://x.com",
            )