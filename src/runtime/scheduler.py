"""
Runtime Scheduler — Phase 3 Checkpoint 2.

The Scheduler decides WHEN cycles run. It is the producer side of the
producer/consumer split between scheduling and queueing.

Per Runtime Model §"Runtime Components" (Scheduler):
- Triggers: manual, scheduled (interval), burst (event-driven), replay
  (deterministic backtest).
- The Scheduler produces WorkItems and enqueues them on a WorkQueue.
- The Executor (consumer) dequeues items and runs them through the Pipeline.

This checkpoint implements:
- ManualTrigger (already exists; scheduler creates WorkItems from explicit
  schedule() calls).
- ScheduledTrigger: time-based with a simple interval (`schedule_interval`).
  Each tick enqueues a cycle WorkItem if enough time has elapsed since the
  last tick.
- BurstTrigger: event-driven; `notify()` enqueues a WorkItem in response to
  an external event (e.g., a new Source observation).

ReplayTrigger is deferred (post-MVP).

Dependency rules:
- Scheduler depends ONLY on `persistence.store.Store` (for any state it
  needs to read/write) and on its collaborators (WorkQueue, PipelineExecutor).
- It MUST NOT import InMemoryStore or any concrete persistence backend.
- All entity lifecycle changes go through `persistence.lifecycle` helpers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from src.core.ids import ID, new_id
from src.core.timestamps import now_utc
from src.runtime.queue import (
    QueueEmptyError,
    WorkItem,
    WorkItemPriority,
    WorkItemStatus,
    WorkQueue,
)

if TYPE_CHECKING:
    from src.persistence.store import Store
    from src.runtime.executor import PipelineExecutor, TriggerResult


@dataclass
class ScheduleConfig:
    """Configuration for a scheduled trigger.

    `interval_seconds` is the minimum time between ticks. Set to None for
    a one-shot trigger that fires once and stops.
    """

    interval_seconds: float | None
    enabled: bool = True
    last_fired_at: str | None = None


@dataclass
class BurstEvent:
    """An external event that triggers a burst cycle.

    Examples: a new Source observation arriving, an alert from an external
    system. Each event becomes one queued WorkItem.
    """

    event_id: ID
    source_id: ID | None = None
    severity: str = "info"  # "info" | "warning" | "critical"
    summary: str = ""


class Scheduler(Protocol):
    """Protocol for Scheduler implementations.

    A Scheduler produces WorkItems. Its concrete implementation in this
    checkpoint is `DefaultScheduler`.
    """

    def schedule(self, trigger_name: str = "manual") -> WorkItem:
        """Enqueue a cycle WorkItem now."""
        ...

    def schedule_interval(self, interval_seconds: float) -> WorkItem | None:
        """Enqueue a cycle if enough time has elapsed since the last tick."""
        ...

    def notify(self, event: BurstEvent) -> WorkItem:
        """Enqueue a burst cycle in response to an external event."""
        ...

    def pending_count(self) -> int:
        ...


@dataclass
class DefaultScheduler:
    """Concrete Scheduler implementation.

    Owns a WorkQueue. Produces WorkItems with appropriate priority and
    metadata. State (last tick timestamp) is kept in-memory; persistence is
    delegated to `Store` if bound (not used for item storage in the MVP).

    This class is stateless beyond its configuration and queue reference;
    it does NOT modify domain Object lifecycles directly. Lifecycle changes
    are handled by the workflow stages via `persistence.lifecycle`.
    """

    queue: WorkQueue
    trigger_name: str = "scheduler"
    schedule_config: ScheduleConfig | None = None
    burst_priority: WorkItemPriority = WorkItemPriority.HIGH
    scheduled_priority: WorkItemPriority = WorkItemPriority.NORMAL
    manual_priority: WorkItemPriority = WorkItemPriority.NORMAL
    burst_severity_priority: dict[str, WorkItemPriority] = field(
        default_factory=lambda: {
            "critical": WorkItemPriority.HIGHEST,
            "warning": WorkItemPriority.HIGH,
            "info": WorkItemPriority.NORMAL,
        }
    )
    _store: "Store | None" = field(default=None, init=False, repr=False)

    def bind_store(self, store: "Store") -> None:
        """Bind a persistence Store.

        The Scheduler does NOT depend on a concrete backend. It accepts the
        abstract `Store` interface only. The MVP does not use the bound store
        for scheduler state; this binding exists for future durable-queue /
        replay support.
        """
        self._store = store

    def schedule(self, trigger_name: str = "manual") -> WorkItem:
        """Enqueue a cycle WorkItem with the manual priority."""
        item = self._make_item(
            priority=self.manual_priority,
            trigger=trigger_name,
        )
        self.queue.enqueue(item)
        return item

    def schedule_interval(self, interval_seconds: float) -> WorkItem | None:
        """Enqueue a cycle if `interval_seconds` has elapsed since the last tick.

        Returns the new WorkItem, or None if the interval has not yet elapsed
        (or scheduling is disabled).
        """
        if self.schedule_config is None:
            self.schedule_config = ScheduleConfig(interval_seconds=interval_seconds)
        elif self.schedule_config.interval_seconds != interval_seconds:
            self.schedule_config.interval_seconds = interval_seconds

        cfg = self.schedule_config
        if not cfg.enabled:
            return None

        if cfg.last_fired_at is not None:
            from datetime import datetime

            try:
                last = datetime.fromisoformat(cfg.last_fired_at.replace("Z", "+00:00"))
                now = datetime.fromisoformat(now_utc().replace("Z", "+00:00"))
                elapsed = (now - last).total_seconds()
                if elapsed < interval_seconds:
                    return None
            except ValueError:
                # Unparseable timestamp; treat as fire-able.
                pass

        item = self._make_item(
            priority=self.scheduled_priority,
            trigger="scheduled",
        )
        self.queue.enqueue(item)
        cfg.last_fired_at = now_utc()
        return item

    def notify(self, event: BurstEvent) -> WorkItem:
        """Enqueue a burst cycle in response to an external event.

        Priority is chosen from `burst_severity_priority` based on
        `event.severity`; falls back to `burst_priority`.
        """
        priority = self.burst_severity_priority.get(event.severity, self.burst_priority)
        item = self._make_item(
            priority=priority,
            trigger="burst",
        )
        # Attach event_id to the item via result_summary so downstream can
        # inspect it. We do not store the full event on the WorkItem to keep
        # the queue small.
        from dataclasses import replace

        item = replace(
            item,
            result_summary=f"burst:{event.event_id}",
        )
        self.queue.enqueue(item)
        return item

    def pending_count(self) -> int:
        return self.queue.size

    def _make_item(self, *, priority: WorkItemPriority, trigger: str) -> WorkItem:
        return WorkItem(
            id=new_id(),
            cycle_id=new_id(),
            priority=priority,
            status=WorkItemStatus.PENDING,
            trigger=trigger,
            enqueued_at=now_utc(),
        )


@dataclass
class CycleDispatcher:
    """Consumes WorkItems from a queue and dispatches them to a PipelineExecutor.

    This is the consumer side that pairs with the Scheduler (producer). It
    implements a single drain step: dequeue one item, run a cycle, record
    the outcome on the item, and return. A separate runner (e.g., the
    Runtime orchestrator) loops over `dispatch_one` until the queue is empty
    or a stop condition is met.

    The dispatcher does NOT depend on a concrete persistence backend; the
    PipelineExecutor handles all persistence through its collaborators.
    """

    executor: "PipelineExecutor"
    queue: WorkQueue

    def dispatch_one(self) -> tuple[WorkItem, "TriggerResult"] | None:
        """Dispatch one WorkItem through the executor.

        Returns:
            A (work_item, trigger_result) tuple, or None if the queue is empty.
        """
        try:
            item = self.queue.dequeue()
        except QueueEmptyError:
            return None

        from src.runtime.executor import PipelineExecutor
        from src.workflow.context import PipelineContext

        if not isinstance(self.executor, PipelineExecutor):
            raise TypeError(
                "CycleDispatcher.executor must be a PipelineExecutor instance"
            )

        context = PipelineContext(cycle_id=item.cycle_id)
        try:
            result = self.executor.run(context)
        except Exception as exc:
            failed = self.queue.mark_failed(item, error=f"{type(exc).__name__}: {exc}")
            return (failed, _error_trigger_result(item, exc))  # type: ignore[return-value]

        completed = self.queue.mark_completed(
            item,
            result_summary=(
                f"signals={result.pipeline_result.signals_emitted}"
                f",research={result.pipeline_result.research_emitted}"
                f",theses={result.pipeline_result.theses_updated}"
            ),
        )
        return (completed, result)

    def drain(self, max_cycles: int | None = None) -> int:
        """Run cycles until the queue is empty or max_cycles is reached.

        Returns:
            Number of cycles dispatched.
        """
        cycles = 0
        while True:
            if max_cycles is not None and cycles >= max_cycles:
                break
            result = self.dispatch_one()
            if result is None:
                break
            cycles += 1
        return cycles


def _error_trigger_result(item: WorkItem, exc: Exception) -> "TriggerResult":
    """Build a minimal TriggerResult for a failed dispatch (used only on exception)."""
    from src.runtime.executor import TriggerResult
    from src.workflow.pipeline import PipelineResult
    from src.core.timestamps import now_utc

    return TriggerResult(
        pipeline_result=PipelineResult(
            cycle_id=item.cycle_id,
            started_at=item.started_at or now_utc(),
            completed_at=now_utc(),
            signals_emitted=0,
            research_emitted=0,
            theses_updated=0,
        ),
        audit_record_count=0,
        triggered_by=item.trigger,
    )


__all__ = [
    "BurstEvent",
    "CycleDispatcher",
    "DefaultScheduler",
    "ScheduleConfig",
    "Scheduler",
]