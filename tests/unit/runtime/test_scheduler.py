"""Tests for the Scheduler and CycleDispatcher (Runtime Checkpoint 2)."""

import pytest

from src.core.entities import Entity, EntityKind
from src.core.ids import ID, new_id
from src.persistence.in_memory import InMemoryStore
from src.persistence.store import Store
from src.runtime.audit import AuditLogger
from src.runtime.executor import PipelineExecutor
from src.runtime.queue import (
    QueueEmptyError,
    WorkItemPriority,
    WorkItemStatus,
    WorkQueue,
)
from src.runtime.scheduler import (
    BurstEvent,
    CycleDispatcher,
    DefaultScheduler,
    ScheduleConfig,
)
from src.workflow.pipeline import Pipeline


def _pipeline() -> Pipeline:
    return Pipeline()


def _executor() -> PipelineExecutor:
    return PipelineExecutor(pipeline=_pipeline(), audit=AuditLogger())


def _entity() -> Entity:
    return Entity.create(kind=EntityKind.COMPANY, name="ACME")


# ----------------------- Manual scheduling -----------------------


class TestManualSchedule:
    def test_schedule_enqueues_one_item(self) -> None:
        q: WorkQueue = WorkQueue()
        s = DefaultScheduler(queue=q)
        item = s.schedule(trigger_name="manual")
        assert item.status == WorkItemStatus.PENDING
        assert item.trigger == "manual"
        assert q.size == 1

    def test_multiple_schedules_in_priority_order(self) -> None:
        q: WorkQueue = WorkQueue()
        s = DefaultScheduler(
            queue=q,
            manual_priority=WorkItemPriority.LOW,
        )
        s.schedule()
        # Switch priority and schedule another — should dequeue first.
        s.manual_priority = WorkItemPriority.HIGH
        s.schedule()
        first = q.dequeue()
        second = q.dequeue()
        assert first.priority == WorkItemPriority.HIGH
        assert second.priority == WorkItemPriority.LOW

    def test_pending_count(self) -> None:
        q: WorkQueue = WorkQueue()
        s = DefaultScheduler(queue=q)
        assert s.pending_count() == 0
        s.schedule()
        s.schedule()
        assert s.pending_count() == 2


# ----------------------- Interval scheduling -----------------------


class TestIntervalSchedule:
    def test_first_tick_fires(self) -> None:
        q: WorkQueue = WorkQueue()
        s = DefaultScheduler(queue=q, schedule_config=ScheduleConfig(interval_seconds=60))
        item = s.schedule_interval(interval_seconds=60)
        assert item is not None
        assert item.trigger == "scheduled"
        assert q.size == 1

    def test_second_tick_within_interval_does_not_fire(self) -> None:
        q: WorkQueue = WorkQueue()
        s = DefaultScheduler(
            queue=q,
            schedule_config=ScheduleConfig(interval_seconds=3600),  # 1 hour
        )
        s.schedule_interval(interval_seconds=3600)
        # Immediately try again — should not fire.
        second = s.schedule_interval(interval_seconds=3600)
        assert second is None
        assert q.size == 1

    def test_disabled_scheduler_does_not_fire(self) -> None:
        q: WorkQueue = WorkQueue()
        cfg = ScheduleConfig(interval_seconds=60, enabled=False)
        s = DefaultScheduler(queue=q, schedule_config=cfg)
        assert s.schedule_interval(interval_seconds=60) is None
        assert q.size == 0

    def test_schedule_config_initialized_on_first_call(self) -> None:
        q: WorkQueue = WorkQueue()
        s = DefaultScheduler(queue=q)
        assert s.schedule_config is None
        s.schedule_interval(interval_seconds=30)
        assert s.schedule_config is not None
        assert s.schedule_config.interval_seconds == 30


# ----------------------- Burst scheduling -----------------------


class TestBurstSchedule:
    def test_notify_enqueues_with_severity_priority(self) -> None:
        q: WorkQueue = WorkQueue()
        s = DefaultScheduler(queue=q)
        event = BurstEvent(
            event_id=new_id(),
            source_id=ID("src-1"),
            severity="critical",
            summary="New SEC filing",
        )
        item = s.notify(event)
        assert item.trigger == "burst"
        assert item.priority == WorkItemPriority.HIGHEST
        assert item.result_summary == f"burst:{event.event_id}"

    def test_burst_severity_priority_mapping(self) -> None:
        q: WorkQueue = WorkQueue()
        s = DefaultScheduler(queue=q)
        # Schedule one of each severity; HIGHEST must dequeue first.
        s.notify(BurstEvent(event_id=new_id(), severity="info"))
        s.notify(BurstEvent(event_id=new_id(), severity="warning"))
        s.notify(BurstEvent(event_id=new_id(), severity="critical"))
        first = q.dequeue()
        second = q.dequeue()
        third = q.dequeue()
        assert first.priority == WorkItemPriority.HIGHEST
        assert second.priority == WorkItemPriority.HIGH
        assert third.priority == WorkItemPriority.NORMAL

    def test_unknown_severity_uses_default(self) -> None:
        q: WorkQueue = WorkQueue()
        s = DefaultScheduler(queue=q, burst_priority=WorkItemPriority.LOW)
        s.notify(BurstEvent(event_id=new_id(), severity="weird"))
        first = q.dequeue()
        assert first.priority == WorkItemPriority.LOW


# ----------------------- Store binding (interface only) -----------------------


class TestSchedulerStoreBinding:
    def test_bind_store_accepts_abstract_interface(self) -> None:
        q: WorkQueue = WorkQueue()
        s = DefaultScheduler(queue=q)
        store: Store = InMemoryStore()  # test boundary only
        # The Scheduler MUST accept the abstract type — proves the runtime
        # layer has no compile-time dependency on InMemoryStore.
        s.bind_store(store)


# ----------------------- CycleDispatcher -----------------------


class TestCycleDispatcher:
    def test_dispatch_one_returns_item_and_result(self) -> None:
        q: WorkQueue = WorkQueue()
        executor = _executor()
        dispatcher = CycleDispatcher(executor=executor, queue=q)
        s = DefaultScheduler(queue=q)
        s.schedule()
        result = dispatcher.dispatch_one()
        assert result is not None
        item, trigger_result = result
        assert item.status == WorkItemStatus.COMPLETED
        assert trigger_result.pipeline_result is not None

    def test_dispatch_one_empty_queue_returns_none(self) -> None:
        q: WorkQueue = WorkQueue()
        dispatcher = CycleDispatcher(executor=_executor(), queue=q)
        assert dispatcher.dispatch_one() is None

    def test_drain_runs_all_pending(self) -> None:
        q: WorkQueue = WorkQueue()
        executor = _executor()
        dispatcher = CycleDispatcher(executor=executor, queue=q)
        s = DefaultScheduler(queue=q)
        for _ in range(5):
            s.schedule()
        assert q.size == 5
        cycles = dispatcher.drain()
        assert cycles == 5
        assert q.size == 0
        assert len(q.completed_items()) == 5

    def test_drain_respects_max_cycles(self) -> None:
        q: WorkQueue = WorkQueue()
        dispatcher = CycleDispatcher(executor=_executor(), queue=q)
        s = DefaultScheduler(queue=q)
        for _ in range(10):
            s.schedule()
        cycles = dispatcher.drain(max_cycles=3)
        assert cycles == 3
        assert q.size == 7

    def test_drain_empty_queue(self) -> None:
        q: WorkQueue = WorkQueue()
        dispatcher = CycleDispatcher(executor=_executor(), queue=q)
        assert dispatcher.drain() == 0

    def test_dispatch_marks_item_completed(self) -> None:
        q: WorkQueue = WorkQueue()
        dispatcher = CycleDispatcher(executor=_executor(), queue=q)
        s = DefaultScheduler(queue=q)
        item = s.schedule()
        result = dispatcher.dispatch_one()
        assert result is not None
        completed, _ = result
        assert completed.id == item.id
        assert completed.status == WorkItemStatus.COMPLETED
        assert completed.result_summary is not None
        assert "signals=" in completed.result_summary

    def test_dispatch_failure_marks_item_failed(self) -> None:
        q: WorkQueue = WorkQueue()

        # Build an executor whose pipeline raises.
        class _ExplodingPipeline:
            def run(self, context: object) -> None:
                raise RuntimeError("kaboom")

            @property
            def stages(self) -> list[object]:
                return []

        executor = PipelineExecutor(pipeline=_ExplodingPipeline(), audit=AuditLogger())  # type: ignore[arg-type]
        dispatcher = CycleDispatcher(executor=executor, queue=q)
        s = DefaultScheduler(queue=q)
        s.schedule()
        result = dispatcher.dispatch_one()
        assert result is not None
        item, _ = result
        assert item.status == WorkItemStatus.FAILED
        assert "kaboom" in (item.error or "")
        assert len(q.failed_items()) == 1


# ----------------------- End-to-end (Scheduler + Dispatcher + Queue) -----------------------


class TestEndToEnd:
    def test_burst_event_runs_cycle_through_pipeline(self) -> None:
        q: WorkQueue = WorkQueue()
        executor = _executor()
        dispatcher = CycleDispatcher(executor=executor, queue=q)
        s = DefaultScheduler(queue=q)
        s.notify(BurstEvent(event_id=new_id(), severity="warning"))
        cycles = dispatcher.drain()
        assert cycles == 1
        assert len(q.completed_items()) == 1
        assert q.completed_items()[0].trigger == "burst"