"""Tests for the PipelineExecutor."""

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
from src.runtime.audit import AuditLogger, EventCategory
from src.runtime.executor import (
    ManualTrigger,
    PipelineExecutor,
    TriggerResult,
)
from src.workflow.context import PipelineContext
from src.workflow.events import StageStarted
from src.workflow.pipeline import Pipeline
from src.workflow.stages import (
    SourceObservationStage,
    default_stages,
)


def make_entity() -> Entity:
    return Entity.create(kind=EntityKind.COMPANY, name="ACME")


def make_signal(entity_id: str) -> Signal:
    return Signal.create(
        entity_ref=EntityRef(id=entity_id, kind="company"),
        type="earnings",
        claim="ACME reported EPS of $1.20, beating consensus by 10%.",
        evidence_ids=("ev-1",),
        direction=SignalDirection.BULLISH,
        horizon=SignalHorizon.SHORT,
        score=Score(0.7, 0.9, 0.8, 0.6, 0.75),
        status=SignalStatus.ACTIVE,
    )


class TestRunEmptyCycle:
    def test_run_empty_pipeline_succeeds(self) -> None:
        pipeline = Pipeline(stages=[])
        audit = AuditLogger()
        executor = PipelineExecutor(pipeline, audit)
        ctx = PipelineContext()
        result = executor.run(ctx)
        assert isinstance(result, TriggerResult)
        assert result.triggered_by == "unknown"  # no trigger passed

    def test_run_with_manual_trigger(self) -> None:
        pipeline = Pipeline(stages=[])
        audit = AuditLogger()
        executor = PipelineExecutor(pipeline, audit)
        ctx = PipelineContext()
        result = executor.run(ctx, trigger=ManualTrigger())
        assert result.triggered_by == "manual"


class TestRunWithStages:
    def test_run_default_stages(self) -> None:
        # Default stages with no implementation interfaces — should all advance
        pipeline = Pipeline(stages=default_stages())
        audit = AuditLogger()
        executor = PipelineExecutor(pipeline, audit)
        ctx = PipelineContext()
        result = executor.run(ctx)
        # No signals/research/theses because no interfaces are wired up
        assert result.pipeline_result.signals_emitted == 0
        assert result.pipeline_result.research_emitted == 0
        assert result.pipeline_result.theses_updated == 0


class TestAuditIntegration:
    def test_audit_records_cycle_start(self) -> None:
        pipeline = Pipeline(stages=[])
        audit = AuditLogger()
        executor = PipelineExecutor(pipeline, audit)
        ctx = PipelineContext()
        executor.run(ctx, trigger=ManualTrigger())
        start_records = audit.query(category=EventCategory.CYCLE, event_type="cycle_start")
        assert len(start_records) == 1
        assert start_records[0].metadata["trigger"] == "manual"

    def test_audit_records_cycle_complete(self) -> None:
        pipeline = Pipeline(stages=[])
        audit = AuditLogger()
        executor = PipelineExecutor(pipeline, audit)
        ctx = PipelineContext()
        executor.run(ctx)
        complete_records = audit.query(
            category=EventCategory.CYCLE, event_type="cycle_complete"
        )
        assert len(complete_records) == 1
        assert complete_records[0].result == "ok"

    def test_audit_records_stage_start(self) -> None:
        pipeline = Pipeline(stages=default_stages())
        audit = AuditLogger()
        executor = PipelineExecutor(pipeline, audit)
        ctx = PipelineContext()
        executor.run(ctx)
        stage_records = audit.query(
            category=EventCategory.STAGE, event_type="stage_start"
        )
        # 6 stages each emit a stage_start event
        assert len(stage_records) == 6

    def test_audit_records_workflow_events(self) -> None:
        pipeline = Pipeline(stages=default_stages())
        audit = AuditLogger()
        executor = PipelineExecutor(pipeline, audit)
        ctx = PipelineContext()
        executor.run(ctx)
        # All stages complete (no implementation interfaces → all gates fail gracefully)
        complete_records = audit.query(event_type="stage_complete")
        # 6 stages, each emits stage_complete
        assert len(complete_records) == 6

    def test_audit_separated_by_cycle_id(self) -> None:
        pipeline = Pipeline(stages=[])
        audit = AuditLogger()
        executor = PipelineExecutor(pipeline, audit)
        ctx1 = PipelineContext()
        ctx2 = PipelineContext()
        executor.run(ctx1)
        executor.run(ctx2)
        records_1 = audit.query(cycle_id=ctx1.cycle_id)
        records_2 = audit.query(cycle_id=ctx2.cycle_id)
        assert len(records_1) >= 2  # start + complete
        assert len(records_2) >= 2
        assert records_1[0].cycle_id == ctx1.cycle_id
        assert records_2[0].cycle_id == ctx2.cycle_id


class TestErrorHandling:
    def test_pipeline_swallows_stage_exception(self) -> None:
        """Pipeline catches stage exceptions and continues (per Workflow Model
        §"Error Recovery Flow" — cycle-level abort is for infrastructure
        failures, not gate failures). The executor records the cycle as
        completed (not aborted) in this case.
        """
        from src.workflow.stages import Stage

        class FailingStage(Stage):
            @property
            def name(self) -> str:
                return "FAIL"

            @property
            def gates(self) -> list:
                return []

            def execute(self, context):
                raise RuntimeError("stage failed")

        pipeline = Pipeline(stages=[FailingStage()])
        audit = AuditLogger()
        executor = PipelineExecutor(pipeline, audit)
        ctx = PipelineContext()
        # No exception propagates; pipeline catches and continues
        result = executor.run(ctx)
        assert isinstance(result, TriggerResult)
        # Cycle completes normally (no abort record)
        complete = audit.query(
            category=EventCategory.CYCLE, event_type="cycle_complete"
        )
        assert len(complete) == 1
        # No abort record
        aborted = audit.query(event_type="cycle_aborted")
        assert len(aborted) == 0


class TestEventClassification:
    def test_stage_started_event_classified_as_stage_start(self) -> None:
        from src.core.timestamps import now_utc

        pipeline = Pipeline(stages=[])
        audit = AuditLogger()
        executor = PipelineExecutor(pipeline, audit)
        ctx = PipelineContext()
        # Manually inject a stage started event
        ctx.events.append(
            StageStarted(cycle_id=ctx.cycle_id, stage_name="S1", started_at=now_utc())
        )
        executor.run(ctx)
        # The event should be classified
        stage_events = audit.query(event_type="stage_start", component="S1")
        assert len(stage_events) == 1

    def test_unknown_event_type_recorded(self) -> None:
        from src.workflow.context import PipelineContext
        from src.core.timestamps import now_utc
        from dataclasses import dataclass

        @dataclass
        class WeirdEvent:
            cycle_id: str
            started_at: str

        pipeline = Pipeline(stages=[])
        audit = AuditLogger()
        executor = PipelineExecutor(pipeline, audit)
        ctx = PipelineContext()
        ctx.events.append(WeirdEvent(cycle_id=ctx.cycle_id, started_at=now_utc()))
        executor.run(ctx)
        # Should be recorded as unknown_event
        unknown = audit.query(event_type="unknown_event")
        assert len(unknown) == 1
