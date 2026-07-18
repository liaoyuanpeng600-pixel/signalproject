"""
PipelineExecutor — wraps the Workflow Pipeline with audit instrumentation.

Per Runtime Model §"Executor":
- Runs each stage's logic (delegated to the Pipeline)
- Forwards stage results to the Validator
- Emits operational events to the Audit Logger
- Persists Objects (delegated to Persistence interface)

Per Runtime Model §"Runtime Boundary":
- Runtime executes the workflow; it does not redefine it.
- All state transitions go through the workflow's domain objects.

This component is a thin orchestration layer:
- Holds a reference to a Pipeline (workflow)
- Holds a reference to an AuditLogger (this package)
- On `run()`, calls pipeline.run(context) and copies events to the AuditLogger

Triggers (per Runtime Model §"Trigger Modes"):
- manual: explicit call to run()
- scheduled: time-based (deferred to a future Scheduler component)
- burst: event-driven (deferred to a future Scheduler component)
- replay: deterministic backtest (deferred)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from src.runtime.audit import AuditLogger, EventCategory
from src.workflow.context import PipelineContext
from src.workflow.events import (
    GateEvaluated,
    ObjectRouted,
    StageCompleted,
    StageStarted,
    WorkflowAborted,
    WorkflowCompleted,
)
from src.workflow.pipeline import Pipeline, PipelineResult


class Trigger(ABC):
    """Base class for cycle triggers.

    A Trigger decides when to run a cycle. Phase 3 implements only the
    ManualTrigger. ScheduledTrigger and BurstTrigger are deferred.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable trigger name."""


class ManualTrigger(Trigger):
    """Manual trigger: cycle is run only when explicitly invoked."""

    @property
    def name(self) -> str:
        return "manual"


@dataclass
class TriggerResult:
    """Result of a triggered cycle execution."""

    pipeline_result: PipelineResult
    audit_record_count: int
    triggered_by: str


class PipelineExecutor:
    """Executes a Pipeline with audit instrumentation.

    Holds a reference to a Pipeline and an AuditLogger. On `run()`,
    invokes `pipeline.run(context)` and copies workflow events to the
    AuditLogger as categorized records.
    """

    def __init__(
        self,
        pipeline: Pipeline,
        audit: AuditLogger,
        component: str = "PipelineExecutor",
    ) -> None:
        self._pipeline = pipeline
        self._audit = audit
        self._component = component

    def run(
        self,
        context: PipelineContext,
        trigger: Trigger | None = None,
    ) -> TriggerResult:
        """Execute a cycle.

        Steps:
        1. Record cycle start in audit log.
        2. Run the pipeline (which mutates context).
        3. Copy workflow events from context to audit log.
        4. Record cycle completion in audit log.
        5. Return a TriggerResult summarizing the cycle.
        """
        cycle_id = context.cycle_id
        trigger_name = trigger.name if trigger else "unknown"

        # Step 1: Cycle start
        self._audit.record(
            cycle_id=cycle_id,
            category=EventCategory.CYCLE,
            component=self._component,
            event_type="cycle_start",
            result="ok",
            metadata={"trigger": trigger_name},
        )

        # Step 2: Run the pipeline
        try:
            pipeline_result = self._pipeline.run(context)
        except Exception as e:
            # Record failure
            self._audit.record(
                cycle_id=cycle_id,
                category=EventCategory.FAILURE,
                component=self._component,
                event_type="cycle_aborted",
                result="error",
                reason=f"{type(e).__name__}: {e}",
            )
            raise

        # Step 3: Copy workflow events to audit log
        self._copy_workflow_events_to_audit(context)

        # Step 4: Cycle completion
        self._audit.record(
            cycle_id=cycle_id,
            category=EventCategory.CYCLE,
            component=self._component,
            event_type="cycle_complete",
            result="ok",
            metadata={
                "signals_emitted": pipeline_result.signals_emitted,
                "research_emitted": pipeline_result.research_emitted,
                "theses_updated": pipeline_result.theses_updated,
            },
        )

        return TriggerResult(
            pipeline_result=pipeline_result,
            audit_record_count=len(self._audit),
            triggered_by=trigger_name,
        )

    def _copy_workflow_events_to_audit(self, context: PipelineContext) -> None:
        """Translate WorkflowContext events into AuditRecords.

        Maps workflow event types to audit categories and event_type strings.
        """
        for event in context.events:
            category, event_type, result, reason, metadata = self._classify_event(event)
            self._audit.record(
                cycle_id=context.cycle_id,
                category=category,
                component=event.stage_name if hasattr(event, "stage_name") else "pipeline",
                event_type=event_type,
                result=result,
                reason=reason,
                metadata=metadata,
            )

    def _classify_event(self, event: object) -> tuple:
        """Map a workflow event to (category, event_type, result, reason, metadata)."""
        if isinstance(event, StageStarted):
            return (EventCategory.STAGE, "stage_start", "ok", None, {})
        if isinstance(event, StageCompleted):
            return (
                EventCategory.STAGE,
                "stage_complete",
                event.status.value,
                None,
                {},
            )
        if isinstance(event, GateEvaluated):
            return (
                EventCategory.GATE,
                "gate_evaluated",
                "pass" if event.passed else "fail",
                event.reason,
                {},
            )
        if isinstance(event, ObjectRouted):
            return (
                EventCategory.OBJECT,
                "object_routed",
                "ok",
                event.reason,
                {"destination": event.destination, "object_kind": event.object_kind},
            )
        if isinstance(event, WorkflowCompleted):
            return (
                EventCategory.CYCLE,
                "workflow_completed",
                "ok",
                None,
                {
                    "signals": event.signals_emitted,
                    "research": event.research_emitted,
                    "theses": event.theses_updated,
                },
            )
        if isinstance(event, WorkflowAborted):
            return (
                EventCategory.FAILURE,
                "workflow_aborted",
                "error",
                event.reason,
                {},
            )
        # Unknown event type — record as cycle-level
        return (EventCategory.CYCLE, "unknown_event", "ok", None, {})
