"""Tests for the Pipeline orchestrator."""

import pytest

from src.core.ids import new_id
from src.workflow.context import PipelineContext
from src.workflow.events import WorkflowCompleted
from src.workflow.pipeline import Pipeline, PipelineResult
from src.workflow.stages import Stage, default_stages


class MockStage(Stage):
    """A stage that does nothing and returns ADVANCE."""

    @property
    def name(self) -> str:
        return self._name

    @property
    def gates(self) -> list:
        return []

    def __init__(self, name: str = "MOCK", outputs: dict | None = None):
        from src.workflow.types import StageResult, StageStatus

        self._name = name
        self._outputs = outputs or {}
        self._result = StageResult(status=StageStatus.ADVANCE, output=self._outputs)

    def execute(self, context: PipelineContext) -> "MockStage._result_type":
        from src.workflow.events import StageCompleted, StageStarted
        from src.core.timestamps import now_utc

        context.emit(
            StageStarted(cycle_id=context.cycle_id, stage_name=self.name, started_at=now_utc())
        )
        context.emit(
            StageCompleted(
                cycle_id=context.cycle_id,
                stage_name=self.name,
                status=self._result.status,
                completed_at=now_utc(),
            )
        )
        return self._result


class FailingStage(Stage):
    """A stage that raises an exception during execution."""

    @property
    def name(self) -> str:
        return "FAILING"

    @property
    def gates(self) -> list:
        return []

    def execute(self, context: PipelineContext):
        raise RuntimeError("stage failure")


class TestPipelineBasics:
    def test_default_stages(self) -> None:
        pipeline = Pipeline()
        assert len(pipeline.stages) == 6

    def test_custom_stages(self) -> None:
        stages = [MockStage("A"), MockStage("B")]
        pipeline = Pipeline(stages=stages)
        assert len(pipeline.stages) == 2


class TestPipelineRun:
    def test_runs_all_stages(self) -> None:
        ctx = PipelineContext()
        pipeline = Pipeline(stages=[MockStage("A"), MockStage("B")])
        result = pipeline.run(ctx)
        assert isinstance(result, PipelineResult)
        assert result.cycle_id == ctx.cycle_id
        assert result.signals_emitted == 0
        assert result.research_emitted == 0
        assert result.theses_updated == 0

    def test_emits_workflow_completed(self) -> None:
        ctx = PipelineContext()
        pipeline = Pipeline(stages=[MockStage("A")])
        pipeline.run(ctx)
        completed_events = [e for e in ctx.events if isinstance(e, WorkflowCompleted)]
        assert len(completed_events) == 1

    def test_continues_on_stage_failure(self) -> None:
        # If a stage raises, the pipeline should continue with the remaining
        # stages (per Workflow Model: cycle-level abort is for infrastructure
        # failures, not gate failures).
        ctx = PipelineContext()
        pipeline = Pipeline(
            stages=[MockStage("A"), FailingStage(), MockStage("C")]
        )
        result = pipeline.run(ctx)
        # Pipeline completes despite the failure
        assert result.cycle_id == ctx.cycle_id
        # All 3 stages still attempted
        events = [e for e in ctx.events if e.__class__.__name__ == "StageStarted"]
        assert len(events) == 2  # A and C; failing one didn't emit


class TestPipelineResult:
    def test_result_fields(self) -> None:
        ctx = PipelineContext()
        pipeline = Pipeline(stages=[MockStage("A")])
        result = pipeline.run(ctx)
        assert result.cycle_id == ctx.cycle_id
        assert result.started_at == ctx.started_at
        assert result.completed_at
        assert result.completed_at >= result.started_at


class TestCycleReport:
    def test_empty_cycle(self) -> None:
        ctx = PipelineContext()
        pipeline = Pipeline(stages=[MockStage("A")])
        result = pipeline.run(ctx)
        report = pipeline.cycle_report(ctx, result)
        assert report["cycle_id"] == ctx.cycle_id
        assert report["signals_emitted"] == 0
        assert report["research_emitted"] == 0
        assert report["theses_updated"] == 0
        assert report["degraded_sources"] == 0
        assert report["rejected_evidences"] == 0
        assert report["held_research"] == 0
        assert report["pending_theses"] == 0

    def test_with_outputs(self) -> None:
        from src.core.signals import (
            EntityRef,
            Signal,
            SignalDirection,
            SignalHorizon,
            SignalStatus,
        )
        from src.core.invariants import Score

        ctx = PipelineContext()
        sig = Signal.create(
            entity_ref=EntityRef(id="e", kind="company"),
            type="earnings",
            claim="ACME reported EPS of $1.20.",
            evidence_ids=("ev-1",),
            direction=SignalDirection.BULLISH,
            horizon=SignalHorizon.SHORT,
            score=Score(0.7, 0.9, 0.8, 0.6, 0.75),
            status=SignalStatus.ACTIVE,
        )
        ctx.signals.append(sig)
        pipeline = Pipeline(stages=[MockStage("A")])
        result = pipeline.run(ctx)
        report = pipeline.cycle_report(ctx, result)
        assert report["signals_emitted"] == 1