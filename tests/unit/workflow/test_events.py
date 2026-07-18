"""Tests for workflow.events."""

import pytest

from src.workflow.events import (
    GateEvaluated,
    ObjectRouted,
    StageCompleted,
    StageStarted,
    WorkflowAborted,
    WorkflowCompleted,
)


class TestStageStarted:
    def test_create(self) -> None:
        from src.core.ids import new_id

        cycle_id = new_id()
        event = StageStarted(cycle_id=cycle_id, stage_name="S1", started_at="2026-07-18T10:00:00+00:00")
        assert event.stage_name == "S1"
        assert event.cycle_id == cycle_id

    def test_frozen(self) -> None:
        from src.core.ids import new_id

        event = StageStarted(cycle_id=new_id(), stage_name="S1", started_at="t")
        with pytest.raises(Exception):
            event.stage_name = "S2"  # type: ignore[misc]


class TestGateEvaluated:
    def test_pass_event(self) -> None:
        from src.core.ids import new_id

        event = GateEvaluated(
            cycle_id=new_id(),
            stage_name="S1",
            gate_id="S1-G1",
            passed=True,
            reason=None,
            evaluated_at="t",
        )
        assert event.passed is True
        assert event.reason is None

    def test_fail_event(self) -> None:
        from src.core.ids import new_id

        event = GateEvaluated(
            cycle_id=new_id(),
            stage_name="S2",
            gate_id="S2-G1",
            passed=False,
            reason="missing source",
            evaluated_at="t",
        )
        assert event.passed is False
        assert event.reason == "missing source"


class TestStageCompleted:
    def test_create(self) -> None:
        from src.workflow.types import StageStatus

        from src.core.ids import new_id

        event = StageCompleted(
            cycle_id=new_id(),
            stage_name="S1",
            status=StageStatus.ADVANCE,
            completed_at="t",
        )
        assert event.status == StageStatus.ADVANCE


class TestObjectRouted:
    def test_create(self) -> None:
        from src.core.ids import new_id

        event = ObjectRouted(
            cycle_id=new_id(),
            stage_name="S2",
            object_id=new_id(),
            object_kind="evidence",
            destination="reject",
            reason="no source attribution",
            routed_at="t",
        )
        assert event.destination == "reject"
        assert event.object_kind == "evidence"


class TestWorkflowCompleted:
    def test_create(self) -> None:
        from src.core.ids import new_id

        event = WorkflowCompleted(
            cycle_id=new_id(),
            started_at="t1",
            completed_at="t2",
            signals_emitted=5,
            research_emitted=3,
            theses_updated=2,
        )
        assert event.signals_emitted == 5
        assert event.research_emitted == 3
        assert event.theses_updated == 2


class TestWorkflowAborted:
    def test_create(self) -> None:
        from src.core.ids import new_id

        event = WorkflowAborted(
            cycle_id=new_id(),
            stage_name="S4",
            reason="persistence unavailable",
            aborted_at="t",
        )
        assert event.reason == "persistence unavailable"