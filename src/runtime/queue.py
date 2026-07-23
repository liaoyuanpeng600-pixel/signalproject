"""
Runtime Queue — Phase 3 Checkpoint 2.

The Queue holds cycle work items in priority order. Each work item represents
a single pipeline cycle to execute. The Queue is consumed by the Scheduler
and dispatched to the PipelineExecutor.

Per Runtime Model §"Runtime Components" (Queue):
- Bounded capacity (max_size); `enqueue` raises when full.
- Priority ordering (lower numeric value = higher priority; ties broken by
  enqueue order — FIFO within a priority class).
- State transitions: PENDING -> RUNNING -> COMPLETED | FAILED.

The Queue depends ONLY on `persistence.store.Store` for any persistence it
needs (currently it stores items in-memory; future implementations can
persist items via the Store interface). It does NOT depend on InMemoryStore.

This module does NOT modify lifecycle state directly. It only enqueues and
dequeues work items; lifecycle transitions for the actual Objects in the
store are performed by the lifecycle helpers.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.ids import ID
    from src.persistence.store import Store


class QueueFullError(Exception):
    """Raised when the queue is at capacity and a new item cannot be enqueued."""


class QueueEmptyError(Exception):
    """Raised when the queue is empty and a dequeue is attempted."""


class InvalidQueueTransition(Exception):
    """Raised when a queue item state transition is not allowed."""

    def __init__(self, current: str, target: str, allowed: list[str]) -> None:
        self.current = current
        self.target = target
        self.allowed = allowed
        super().__init__(
            f"Invalid queue item transition: {current!r} -> {target!r}. "
            f"Allowed targets: {allowed}"
        )


class WorkItemStatus(str, Enum):
    """Lifecycle states for a queued work item."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# Allowed state transitions for a work item.
_WORK_ITEM_TRANSITIONS: dict[WorkItemStatus, frozenset[WorkItemStatus]] = {
    WorkItemStatus.PENDING: frozenset({WorkItemStatus.RUNNING, WorkItemStatus.CANCELLED}),
    WorkItemStatus.RUNNING: frozenset({WorkItemStatus.COMPLETED, WorkItemStatus.FAILED}),
    WorkItemStatus.COMPLETED: frozenset(),
    WorkItemStatus.FAILED: frozenset(),
    WorkItemStatus.CANCELLED: frozenset(),
}


class WorkItemPriority(int, Enum):
    """Canonical priority classes.

    Lower numeric value = higher priority. HIGHEST (0) runs first.
    """

    HIGHEST = 0
    HIGH = 10
    NORMAL = 50
    LOW = 90
    LOWEST = 100


@dataclass(frozen=True, slots=True)
class WorkItem:
    """A unit of work for the runtime.

    Fields:
        id: Unique ID for this work item.
        cycle_id: The pipeline cycle this item represents.
        priority: Priority class (lower value = higher priority).
        status: Current queue state.
        trigger: Name of the trigger that produced this item (e.g., "manual",
            "scheduled", "burst").
        enqueued_at: ISO8601 UTC timestamp of enqueue.
        started_at: ISO8601 UTC timestamp when the item left the queue, if
            applicable.
        completed_at: ISO8601 UTC timestamp when the item reached a terminal
            state, if applicable.
        result_summary: Optional summary of the cycle result after completion.
        error: Optional error string when status == FAILED.
    """

    id: "ID"
    cycle_id: "ID"
    priority: WorkItemPriority = WorkItemPriority.NORMAL
    status: WorkItemStatus = WorkItemStatus.PENDING
    trigger: str = "manual"
    enqueued_at: str = ""
    started_at: str | None = None
    completed_at: str | None = None
    result_summary: str | None = None
    error: str | None = None

    def transition(self, target: WorkItemStatus) -> "WorkItem":
        """Return a new WorkItem with the given status, validating the transition.

        Raises:
            InvalidQueueTransition: If the transition is not in the allowed graph.
        """
        allowed = _WORK_ITEM_TRANSITIONS.get(self.status, frozenset())
        if target not in allowed:
            raise InvalidQueueTransition(
                self.status.value, target.value, sorted(s.value for s in allowed)
            )
        # dataclasses.replace() preserves frozen-ness.
        from dataclasses import replace

        return replace(self, status=target)


@dataclass
class QueueStats:
    """Snapshot of queue counters at a point in time."""

    pending: int
    running: int
    completed: int
    failed: int
    cancelled: int
    capacity_used: int
    capacity_max: int | None


class WorkQueue:
    """Bounded priority queue of WorkItems.

    - Capacity is optional (None = unbounded).
    - Lower priority numeric value = higher priority; ties broken FIFO.
    - State transitions are validated per `_WORK_ITEM_TRANSITIONS`.

    The Queue itself does NOT depend on persistence. Items are stored in
    process memory. Callers (Scheduler) can persist a snapshot via the
    `Store` interface if needed; this is a deliberate MVP scoping choice
    (post-MVP: durable queue).
    """

    def __init__(self, max_size: int | None = None) -> None:
        """Create a new WorkQueue.

        Args:
            max_size: Optional capacity. None means unbounded.
        """
        if max_size is not None and max_size <= 0:
            raise ValueError("max_size must be positive or None")
        self._max_size = max_size
        # Bucket items by priority class; each bucket is a deque (FIFO within
        # priority). Items are added to the bucket's tail and removed from
        # its head.
        self._buckets: dict[WorkItemPriority, deque[WorkItem]] = {}
        # Keep track of terminal-state items so callers can inspect outcomes.
        self._completed: list[WorkItem] = []
        self._failed: list[WorkItem] = []
        self._cancelled: list[WorkItem] = []
        # Monotonic counter to break FIFO ties deterministically.
        self._seq = 0
        # Optional reference to a Store for future durable-queue work.
        # Runtime code MUST go through this interface, never InMemoryStore.
        self._store: "Store | None" = None

    # ---- configuration ----

    @property
    def max_size(self) -> int | None:
        return self._max_size

    @property
    def size(self) -> int:
        """Number of PENDING items currently in the queue (excluding running/terminal)."""
        return sum(len(b) for b in self._buckets.values())

    def bind_store(self, store: "Store") -> None:
        """Bind a persistence Store to this queue.

        The Store is NOT used for item storage in the MVP. It is reserved for
        future durable-queue support. Runtime code MUST go through this
        interface only — it must NOT import InMemoryStore.
        """
        self._store = store

    # ---- enqueue / dequeue ----

    def enqueue(self, item: WorkItem) -> None:
        """Add an item to the queue.

        Items must be PENDING to be enqueued; re-enqueueing a terminal item is
        not supported (use a fresh WorkItem).

        Raises:
            QueueFullError: If the queue is at capacity.
            ValueError: If the item is not PENDING.
        """
        if item.status != WorkItemStatus.PENDING:
            raise ValueError(
                f"Only PENDING items can be enqueued; got status={item.status.value}"
            )
        if self._max_size is not None and self.size >= self._max_size:
            raise QueueFullError(
                f"Queue is full ({self.size}/{self._max_size}); cannot enqueue"
            )
        bucket = self._buckets.setdefault(item.priority, deque())
        bucket.append(item)
        self._seq += 1

    def dequeue(self) -> WorkItem:
        """Remove and return the highest-priority item, transitioned to RUNNING.

        Raises:
            QueueEmptyError: If no PENDING items exist.
        """
        if self.size == 0:
            raise QueueEmptyError("Queue is empty; cannot dequeue")
        # Iterate priority classes from lowest numeric value to highest.
        for priority in sorted(self._buckets.keys(), key=lambda p: int(p)):
            bucket = self._buckets[priority]
            if bucket:
                item = bucket.popleft()
                started = item.transition(WorkItemStatus.RUNNING)
                # Preserve started_at; downstream may want to stamp it.
                if started.started_at is None:
                    from src.core.timestamps import now_utc
                    from dataclasses import replace

                    started = replace(started, started_at=now_utc())
                return started
        # Unreachable, but be explicit.
        raise QueueEmptyError("Queue is empty; cannot dequeue")

    def peek(self) -> WorkItem | None:
        """Return the highest-priority PENDING item without removing it."""
        for priority in sorted(self._buckets.keys(), key=lambda p: int(p)):
            bucket = self._buckets[priority]
            if bucket:
                return bucket[0]
        return None

    # ---- state transitions for dequeued items ----

    def mark_completed(self, item: WorkItem, result_summary: str | None = None) -> WorkItem:
        """Transition a RUNNING item to COMPLETED. Item must have been dequeued from this queue.

        Raises:
            InvalidQueueTransition: If the item is not RUNNING.
        """
        completed = item.transition(WorkItemStatus.COMPLETED)
        if result_summary is not None:
            from dataclasses import replace

            completed = replace(completed, result_summary=result_summary)
        self._completed.append(completed)
        return completed

    def mark_failed(self, item: WorkItem, error: str) -> WorkItem:
        """Transition a RUNNING item to FAILED."""
        failed = item.transition(WorkItemStatus.FAILED)
        from dataclasses import replace

        failed = replace(failed, error=error)
        self._failed.append(failed)
        return failed

    def cancel(self, item: WorkItem) -> WorkItem:
        """Transition a PENDING item to CANCELLED. Must NOT have been dequeued yet."""
        cancelled = item.transition(WorkItemStatus.CANCELLED)
        self._cancelled.append(cancelled)
        # The cancelled item has a different status than the bucketed one
        # (since dataclass equality compares all fields), so we remove by ID.
        bucket = self._buckets.get(item.priority)
        if bucket is not None:
            for idx, queued in enumerate(bucket):
                if str(queued.id) == str(item.id):
                    del bucket[idx]
                    break
        return cancelled

    # ---- introspection ----

    def stats(self) -> QueueStats:
        """Return a snapshot of queue counters."""
        return QueueStats(
            pending=self.size,
            running=0,  # MVP: running items are immediately terminalized on completion
            completed=len(self._completed),
            failed=len(self._failed),
            cancelled=len(self._cancelled),
            capacity_used=self.size,
            capacity_max=self._max_size,
        )

    def completed_items(self) -> tuple[WorkItem, ...]:
        return tuple(self._completed)

    def failed_items(self) -> tuple[WorkItem, ...]:
        return tuple(self._failed)

    def cancelled_items(self) -> tuple[WorkItem, ...]:
        return tuple(self._cancelled)

    def clear(self) -> None:
        """Remove all items from the queue and reset terminal-item logs.

        Used by tests and for cold restart.
        """
        self._buckets.clear()
        self._completed.clear()
        self._failed.clear()
        self._cancelled.clear()
        self._seq = 0


__all__ = [
    "InvalidQueueTransition",
    "QueueEmptyError",
    "QueueFullError",
    "QueueStats",
    "WorkItem",
    "WorkItemPriority",
    "WorkItemStatus",
    "WorkQueue",
]