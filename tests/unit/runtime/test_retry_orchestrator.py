"""Tests for RetryOrchestrator (Runtime Checkpoint 4)."""

from typing import Any

import pytest

from src.core.ids import ID, new_id
from src.runtime.audit import AuditLogger
from src.runtime.cycle import CycleReport, RuntimeCycle
from src.runtime.dead_letter import DeadLetterQueue
from src.runtime.executor import PipelineExecutor
from src.runtime.queue import (
    WorkItem,
    WorkItemPriority,
    WorkItemStatus,
    WorkQueue,
)
from src.runtime.retry import RetryPolicy, RetryPolicyKind
from src.runtime.retry_manager import RetryContext, RetryManager
from src.runtime.retry_orchestrator import RetryOrchestrator, RetryOutcome
from src.runtime.validator import StageValidation, ValidationReport, Validator
from src.workflow.pipeline import Pipeline


# ----------------------- helpers -----------------------


def _item(status: WorkItemStatus = WorkItemStatus.FAILED) -> WorkItem:
    return WorkItem(
        id=new_id(),
        cycle_id=new_id(),
        priority=WorkItemPriority.NORMAL,
        status=status,
        trigger="manual",
        enqueued_at="2026-07-19T00:00:00Z",
    )


def _cycle_report(error: str | None = None) -> CycleReport:
    return CycleReport(
        cycle_id=new_id(),
        started_at="2026-07-19T00:00:00Z",
        completed_at="2026-07-19T00:00:01Z",
        signals_emitted=0,
        research_emitted=0,
        theses_updated=0,
        sources_loaded=0,
        entities_loaded=0,
        validation_passed=False,
        gates_total=1,
        gates_passed=0,
        gates_failed=1,
        signals_persisted=0,
        research_persisted=0,
        theses_persisted=0,
        error=error,
    )


def _validation() -> ValidationReport:
    return ValidationReport(
        cycle_id="c1",
        stage_validations=(
            StageValidation(
                stage_name="S1",
                gate_count=1,
                passed_count=0,
                failed_count=1,
                first_failure=("S1-G1", "fail"),
                evaluations=(("S1-G1", False, "fail"),),
            ),
        ),
        total_gates=1,
        total_passed=0,
        total_failed=1,
    )


# ----------------------- retry path -----------------------


class TestRetryPath:
    def test_immediate_retry_enqueues_new_item(self) -> None:
        q: WorkQueue = WorkQueue()
        dlq: DeadLetterQueue = DeadLetterQueue()
        mgr = RetryManager(RetryPolicy(kind=RetryPolicyKind.IMMEDIATE, max_attempts=3))
        orch = RetryOrchestrator(mgr, q, dlq)

        original = _item()
        outcome = orch.handle_failed_cycle(
            original_item=original,
            validation=_validation(),
            cycle_report=_cycle_report(),
            attempt=1,
        )

        assert outcome.decision_route == "retry"
        assert outcome.retry_item_id is not None
        assert q.size == 1
        assert dlq.size == 0

    def test_retry_uses_fresh_work_item_with_same_cycle(self) -> None:
        q: WorkQueue = WorkQueue()
        mgr = RetryManager(RetryPolicy(kind=RetryPolicyKind.IMMEDIATE, max_attempts=3))
        orch = RetryOrchestrator(mgr, q, DeadLetterQueue())

        original = _item()
        original_cycle = original.cycle_id

        orch.handle_failed_cycle(
            original_item=original,
            validation=_validation(),
            cycle_report=_cycle_report(),
            attempt=1,
        )

        dequeued = q.dequeue()
        assert dequeued.cycle_id == original_cycle
        assert dequeued.trigger == "retry"
        assert dequeued.status == WorkItemStatus.RUNNING

    def test_retry_priority_propagates(self) -> None:
        q: WorkQueue = WorkQueue()
        mgr = RetryManager(RetryPolicy(kind=RetryPolicyKind.IMMEDIATE, max_attempts=3))
        orch = RetryOrchestrator(mgr, q, DeadLetterQueue())
        original = _item()
        orch.handle_failed_cycle(
            original_item=original,
            validation=_validation(),
            cycle_report=_cycle_report(),
            attempt=1,
            retry_priority=WorkItemPriority.HIGH,
        )
        dequeued = q.dequeue()
        assert dequeued.priority == WorkItemPriority.HIGH


# ----------------------- dead-letter path -----------------------


class TestDeadLetterPath:
    def test_manual_policy_routes_to_dlq(self) -> None:
        q: WorkQueue = WorkQueue()
        dlq: DeadLetterQueue = DeadLetterQueue()
        mgr = RetryManager(RetryPolicy(kind=RetryPolicyKind.MANUAL, max_attempts=10))
        orch = RetryOrchestrator(mgr, q, dlq)

        original = _item()
        outcome = orch.handle_failed_cycle(
            original_item=original,
            validation=_validation(),
            cycle_report=_cycle_report(),
            attempt=1,
        )

        assert outcome.decision_route == "dead_letter"
        assert outcome.dead_lettered is True
        assert dlq.size == 1
        assert q.size == 0

    def test_budget_exhausted_routes_to_dlq(self) -> None:
        q: WorkQueue = WorkQueue()
        dlq: DeadLetterQueue = DeadLetterQueue()
        mgr = RetryManager(
            RetryPolicy(kind=RetryPolicyKind.IMMEDIATE, max_attempts=2)
        )
        orch = RetryOrchestrator(mgr, q, dlq)

        original = _item()
        # attempt=2 == max_attempts → exhausted
        outcome = orch.handle_failed_cycle(
            original_item=original,
            validation=_validation(),
            cycle_report=_cycle_report(),
            attempt=2,
        )

        assert outcome.decision_route == "dead_letter"
        assert dlq.size == 1

    def test_infrastructure_failure_routes_to_dlq(self) -> None:
        q: WorkQueue = WorkQueue()
        dlq: DeadLetterQueue = DeadLetterQueue()
        mgr = RetryManager(
            RetryPolicy(kind=RetryPolicyKind.EXPONENTIAL, max_attempts=10)
        )
        orch = RetryOrchestrator(mgr, q, dlq)
        original = _item()
        outcome = orch.handle_failed_cycle(
            original_item=original,
            validation=_validation(),
            cycle_report=_cycle_report(error="store kaboom"),
            attempt=1,
        )
        assert outcome.decision_route == "dead_letter"
        assert "store kaboom" in dlq.list_entries()[0].reason

    def test_dlq_marks_original_item_failed(self) -> None:
        q: WorkQueue = WorkQueue()
        dlq: DeadLetterQueue = DeadLetterQueue()
        mgr = RetryManager(RetryPolicy(kind=RetryPolicyKind.MANUAL))
        orch = RetryOrchestrator(mgr, q, dlq)

        # Build a PENDING item, enqueue, dequeue (transitions to RUNNING).
        pending = _item(WorkItemStatus.PENDING)
        q.enqueue(pending)
        dequeued = q.dequeue()  # now RUNNING
        assert dequeued.status == WorkItemStatus.RUNNING

        orch.handle_failed_cycle(
            original_item=dequeued,
            validation=_validation(),
            cycle_report=_cycle_report(),
            attempt=1,
        )
        # Original item is now in queue's failed log.
        assert len(q.failed_items()) == 1
        assert q.failed_items()[0].id == dequeued.id


# ----------------------- replay from DLQ -----------------------


class TestReplayFromDLQ:
    def test_replay_pops_and_enqueues(self) -> None:
        q: WorkQueue = WorkQueue()
        dlq: DeadLetterQueue = DeadLetterQueue()
        mgr = RetryManager(RetryPolicy(kind=RetryPolicyKind.MANUAL))
        orch = RetryOrchestrator(mgr, q, dlq)

        original = _item()
        dlq.enqueue(original, reason="x", attempt=1)

        outcome = orch.handle_replay_from_dead_letter()
        assert outcome is not None
        assert outcome.decision_route == "retry"
        assert outcome.retry_item_id is not None
        assert q.size == 1
        assert dlq.size == 0

    def test_replay_empty_dlq_returns_none(self) -> None:
        q: WorkQueue = WorkQueue()
        dlq: DeadLetterQueue = DeadLetterQueue()
        mgr = RetryManager(RetryPolicy(kind=RetryPolicyKind.MANUAL))
        orch = RetryOrchestrator(mgr, q, dlq)

        outcome = orch.handle_replay_from_dead_letter()
        assert outcome is None


# ----------------------- end-to-end with RuntimeCycle -----------------------


class TestEndToEnd:
    def test_immediate_retry_then_success(self) -> None:
        """A failing cycle that retries under IMMEDIATE policy.

        We simulate this by feeding two CycleReports: one failing (route to
        retry), and a synthetic cycle that the retry will run. We only
        verify the orchestration path; the actual retry cycle is the same
        RuntimeCycle.run() call.
        """
        from src.runtime.executor import PipelineExecutor

        q: WorkQueue = WorkQueue()
        dlq: DeadLetterQueue = DeadLetterQueue()
        mgr = RetryManager(
            RetryPolicy(kind=RetryPolicyKind.IMMEDIATE, max_attempts=3)
        )
        orch = RetryOrchestrator(mgr, q, dlq)

        original = _item()
        out = orch.handle_failed_cycle(
            original_item=original,
            validation=_validation(),
            cycle_report=_cycle_report(),
            attempt=1,
        )
        assert out.decision_route == "retry"

        # The retry queue now has one item; consuming it via RuntimeCycle
        # produces a fresh CycleReport.
        runtime = RuntimeCycle(
            pipeline=Pipeline(),
            executor=PipelineExecutor(pipeline=Pipeline(), audit=AuditLogger()),
            validator=Validator(),
            store=None,  # type: ignore[arg-type]
            audit=AuditLogger(),
        )
        # Drain the queue manually.
        retry_item = q.dequeue()
        assert retry_item.trigger == "retry"


# ----------------------- dep-inversion -----------------------


class TestDepInversion:
    def test_orchestrator_does_not_import_concrete_store(self) -> None:
        import re

        for module_name in (
            "src.runtime.retry_orchestrator",
            "src.runtime.retry_manager",
            "src.runtime.retry",
            "src.runtime.dead_letter",
        ):
            import importlib

            mod = importlib.import_module(module_name)
            source_path = mod.__file__ or ""
            with open(source_path, encoding="utf-8") as f:
                contents = f.read()
            import_re = re.compile(
                r"^\s*(?:from\s+src\.persistence\.in_memory|import\s+src\.persistence\.in_memory)",
                re.MULTILINE,
            )
            assert not import_re.search(contents), module_name

    def test_orchestrator_does_not_import_workflow_gates(self) -> None:
        import importlib

        for module_name in (
            "src.runtime.retry_orchestrator",
            "src.runtime.retry_manager",
            "src.runtime.retry",
        ):
            mod = importlib.import_module(module_name)
            source_path = mod.__file__ or ""
            with open(source_path, encoding="utf-8") as f:
                contents = f.read()
            assert "from src.workflow.gates" not in contents, module_name
            assert "from src.workflow.stages" not in contents, module_name