"""Tests for the WorkQueue (Runtime Checkpoint 2)."""

from datetime import datetime, timezone

import pytest

from src.core.entities import Entity, EntityKind
from src.core.ids import ID, new_id
from src.persistence.in_memory import InMemoryStore  # used by tests ONLY (not runtime)
from src.persistence.store import Store
from src.runtime.queue import (
    InvalidQueueTransition,
    QueueEmptyError,
    QueueFullError,
    WorkItem,
    WorkItemPriority,
    WorkItemStatus,
    WorkQueue,
)


def _make_item(
    *,
    priority: WorkItemPriority = WorkItemPriority.NORMAL,
    trigger: str = "manual",
    cycle_id: ID | None = None,
) -> WorkItem:
    return WorkItem(
        id=new_id(),
        cycle_id=cycle_id or new_id(),
        priority=priority,
        status=WorkItemStatus.PENDING,
        trigger=trigger,
        enqueued_at="2026-07-19T00:00:00Z",
    )


# ----------------------- Enqueue / dequeue -----------------------


class TestEnqueueDequeue:
    def test_enqueue_then_dequeue(self) -> None:
        q: WorkQueue = WorkQueue()
        item = _make_item()
        q.enqueue(item)
        assert q.size == 1
        dequeued = q.dequeue()
        assert dequeued.id == item.id
        assert dequeued.status == WorkItemStatus.RUNNING

    def test_dequeue_empty_raises(self) -> None:
        q: WorkQueue = WorkQueue()
        with pytest.raises(QueueEmptyError):
            q.dequeue()

    def test_enqueue_non_pending_raises(self) -> None:
        q: WorkQueue = WorkQueue()
        # Force an item into RUNNING without going through the queue.
        running_item = _make_item().transition(WorkItemStatus.RUNNING)
        with pytest.raises(ValueError):
            q.enqueue(running_item)

    def test_clear_resets_queue(self) -> None:
        q: WorkQueue = WorkQueue()
        q.enqueue(_make_item())
        q.enqueue(_make_item())
        q.clear()
        assert q.size == 0


# ----------------------- Priority -----------------------


class TestPriority:
    def test_higher_priority_dequeued_first(self) -> None:
        q: WorkQueue = WorkQueue()
        low = _make_item(priority=WorkItemPriority.LOW)
        high = _make_item(priority=WorkItemPriority.HIGH)
        normal = _make_item(priority=WorkItemPriority.NORMAL)
        q.enqueue(low)
        q.enqueue(high)
        q.enqueue(normal)

        first = q.dequeue()
        second = q.dequeue()
        third = q.dequeue()

        assert first.id == high.id
        assert second.id == normal.id
        assert third.id == low.id

    def test_fifo_within_same_priority(self) -> None:
        q: WorkQueue = WorkQueue()
        a = _make_item(priority=WorkItemPriority.NORMAL)
        b = _make_item(priority=WorkItemPriority.NORMAL)
        c = _make_item(priority=WorkItemPriority.NORMAL)
        q.enqueue(a)
        q.enqueue(b)
        q.enqueue(c)

        assert q.dequeue().id == a.id
        assert q.dequeue().id == b.id
        assert q.dequeue().id == c.id

    def test_peek_does_not_remove(self) -> None:
        q: WorkQueue = WorkQueue()
        high = _make_item(priority=WorkItemPriority.HIGH)
        q.enqueue(high)
        assert q.peek() is not None
        assert q.peek().id == high.id
        assert q.size == 1

    def test_peek_returns_none_when_empty(self) -> None:
        q: WorkQueue = WorkQueue()
        assert q.peek() is None

    def test_priority_classes_are_disjoint(self) -> None:
        # Sanity: each priority class has a distinct numeric value.
        values = {int(p) for p in WorkItemPriority}
        assert len(values) == len(WorkItemPriority)


# ----------------------- Bounded capacity -----------------------


class TestBoundedCapacity:
    def test_enqueue_full_raises(self) -> None:
        q: WorkQueue = WorkQueue(max_size=2)
        q.enqueue(_make_item())
        q.enqueue(_make_item())
        with pytest.raises(QueueFullError):
            q.enqueue(_make_item())

    def test_max_size_must_be_positive(self) -> None:
        with pytest.raises(ValueError):
            WorkQueue(max_size=0)
        with pytest.raises(ValueError):
            WorkQueue(max_size=-1)

    def test_unbounded_queue(self) -> None:
        q: WorkQueue = WorkQueue()
        for _ in range(100):
            q.enqueue(_make_item())
        assert q.size == 100

    def test_stats_capacity(self) -> None:
        q: WorkQueue = WorkQueue(max_size=5)
        q.enqueue(_make_item())
        q.enqueue(_make_item())
        stats = q.stats()
        assert stats.capacity_used == 2
        assert stats.capacity_max == 5


# ----------------------- State transitions -----------------------


class TestWorkItemTransitions:
    def test_pending_to_running(self) -> None:
        item = _make_item()
        running = item.transition(WorkItemStatus.RUNNING)
        assert running.status == WorkItemStatus.RUNNING

    def test_running_to_completed(self) -> None:
        running = _make_item().transition(WorkItemStatus.RUNNING)
        done = running.transition(WorkItemStatus.COMPLETED)
        assert done.status == WorkItemStatus.COMPLETED

    def test_running_to_failed(self) -> None:
        running = _make_item().transition(WorkItemStatus.RUNNING)
        failed = running.transition(WorkItemStatus.FAILED)
        assert failed.status == WorkItemStatus.FAILED

    def test_pending_to_cancelled(self) -> None:
        cancelled = _make_item().transition(WorkItemStatus.CANCELLED)
        assert cancelled.status == WorkItemStatus.CANCELLED

    def test_completed_is_terminal(self) -> None:
        done = (
            _make_item()
            .transition(WorkItemStatus.RUNNING)
            .transition(WorkItemStatus.COMPLETED)
        )
        with pytest.raises(InvalidQueueTransition):
            done.transition(WorkItemStatus.RUNNING)

    def test_failed_is_terminal(self) -> None:
        failed = (
            _make_item()
            .transition(WorkItemStatus.RUNNING)
            .transition(WorkItemStatus.FAILED)
        )
        with pytest.raises(InvalidQueueTransition):
            failed.transition(WorkItemStatus.RUNNING)

    def test_cancelled_is_terminal(self) -> None:
        cancelled = _make_item().transition(WorkItemStatus.CANCELLED)
        with pytest.raises(InvalidQueueTransition):
            cancelled.transition(WorkItemStatus.PENDING)

    def test_running_to_cancelled_disallowed(self) -> None:
        # Per state graph: RUNNING can only go to COMPLETED or FAILED.
        running = _make_item().transition(WorkItemStatus.RUNNING)
        with pytest.raises(InvalidQueueTransition):
            running.transition(WorkItemStatus.CANCELLED)

    def test_pending_to_completed_disallowed(self) -> None:
        # Must pass through RUNNING.
        with pytest.raises(InvalidQueueTransition):
            _make_item().transition(WorkItemStatus.COMPLETED)


class TestQueueTransitionHelpers:
    def test_mark_completed_appends(self) -> None:
        q: WorkQueue = WorkQueue()
        item = _make_item()
        q.enqueue(item)
        running = q.dequeue()
        completed = q.mark_completed(running, result_summary="ok")
        assert completed.status == WorkItemStatus.COMPLETED
        assert completed.result_summary == "ok"
        assert len(q.completed_items()) == 1

    def test_mark_failed_appends(self) -> None:
        q: WorkQueue = WorkQueue()
        item = _make_item()
        q.enqueue(item)
        running = q.dequeue()
        failed = q.mark_failed(running, error="boom")
        assert failed.status == WorkItemStatus.FAILED
        assert failed.error == "boom"
        assert len(q.failed_items()) == 1

    def test_cancel_removes_from_bucket(self) -> None:
        q: WorkQueue = WorkQueue()
        item = _make_item()
        q.enqueue(item)
        cancelled = q.cancel(item)
        assert cancelled.status == WorkItemStatus.CANCELLED
        assert q.size == 0
        assert len(q.cancelled_items()) == 1

    def test_mark_completed_requires_running(self) -> None:
        q: WorkQueue = WorkQueue()
        pending = _make_item()
        with pytest.raises(InvalidQueueTransition):
            q.mark_completed(pending)

    def test_mark_failed_requires_running(self) -> None:
        q: WorkQueue = WorkQueue()
        pending = _make_item()
        with pytest.raises(InvalidQueueTransition):
            q.mark_failed(pending, error="nope")

    def test_cancel_requires_pending(self) -> None:
        q: WorkQueue = WorkQueue()
        running = _make_item().transition(WorkItemStatus.RUNNING)
        with pytest.raises(InvalidQueueTransition):
            q.cancel(running)


# ----------------------- Stats -----------------------


class TestStats:
    def test_initial_stats(self) -> None:
        q: WorkQueue = WorkQueue()
        stats = q.stats()
        assert stats.pending == 0
        assert stats.completed == 0
        assert stats.failed == 0
        assert stats.cancelled == 0

    def test_stats_after_lifecycle(self) -> None:
        q: WorkQueue = WorkQueue(max_size=10)
        for _ in range(3):
            q.enqueue(_make_item())
        q.dequeue()
        # Manually complete the running item.
        # Re-fetch by tracking — for test simplicity use the dequeued reference.
        # Already consumed; use peek-or-cancel on remaining two.
        q.enqueue(_make_item(priority=WorkItemPriority.LOW))
        # Cancel one of the pending items.
        pending = q.peek()
        assert pending is not None
        q.cancel(pending)
        stats = q.stats()
        assert stats.pending == 2
        assert stats.cancelled == 1


# ----------------------- Store binding (interface, not impl) -----------------------


class TestStoreBinding:
    def test_bind_store_accepts_store_interface(self) -> None:
        """Queue MUST accept the abstract Store interface, not a concrete impl.

        This test uses InMemoryStore as the concrete backend ONLY at the
        test boundary; the queue itself sees only the `Store` type.
        """
        store: Store = InMemoryStore()
        q: WorkQueue = WorkQueue()
        # Should not raise — Queue's API takes the abstract type.
        q.bind_store(store)

    def test_store_is_optional(self) -> None:
        q: WorkQueue = WorkQueue()
        # No bind_store() call; operations still work.
        q.enqueue(_make_item())
        assert q.size == 1


# ----------------------- WorkItem immutability -----------------------


class TestWorkItemFrozen:
    def test_workitem_is_frozen(self) -> None:
        item = _make_item()
        with pytest.raises(Exception):  # FrozenInstanceError
            item.priority = WorkItemPriority.HIGH  # type: ignore[misc]

    def test_transition_returns_new_instance(self) -> None:
        item = _make_item()
        running = item.transition(WorkItemStatus.RUNNING)
        assert item.status == WorkItemStatus.PENDING  # original unchanged
        assert running.status == WorkItemStatus.RUNNING
        assert running is not item

    def test_cycle_id_preserved_through_transitions(self) -> None:
        cycle = new_id()
        item = _make_item(cycle_id=cycle)
        running = item.transition(WorkItemStatus.RUNNING)
        done = running.transition(WorkItemStatus.COMPLETED)
        assert done.cycle_id == cycle