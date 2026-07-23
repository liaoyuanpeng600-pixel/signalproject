"""Tests for DeadLetterQueue (Runtime Checkpoint 4)."""

import pytest

from src.core.ids import ID, new_id
from src.runtime.dead_letter import DeadLetterEntry, DeadLetterQueue
from src.runtime.queue import WorkItem, WorkItemPriority, WorkItemStatus


def _make_item() -> WorkItem:
    return WorkItem(
        id=new_id(),
        cycle_id=new_id(),
        priority=WorkItemPriority.NORMAL,
        status=WorkItemStatus.FAILED,
        trigger="manual",
        enqueued_at="2026-07-19T00:00:00Z",
    )


class TestDeadLetterBasics:
    def test_empty_initially(self) -> None:
        dlq = DeadLetterQueue()
        assert dlq.size == 0
        assert dlq.list_entries() == ()

    def test_enqueue_adds_entry(self) -> None:
        dlq = DeadLetterQueue()
        item = _make_item()
        added = dlq.enqueue(item, reason="kaboom", attempt=3)
        assert added is True
        assert dlq.size == 1

    def test_entry_preserves_item(self) -> None:
        dlq = DeadLetterQueue()
        item = _make_item()
        dlq.enqueue(item, reason="kaboom", attempt=2)
        entries = dlq.list_entries()
        assert len(entries) == 1
        e = entries[0]
        assert e.item is item
        assert e.reason == "kaboom"
        assert e.attempt == 2
        assert e.dead_lettered_at != ""

    def test_clear(self) -> None:
        dlq = DeadLetterQueue()
        dlq.enqueue(_make_item(), reason="x", attempt=1)
        dlq.clear()
        assert dlq.size == 0


class TestDeadLetterBounds:
    def test_max_size_must_be_positive(self) -> None:
        with pytest.raises(ValueError):
            DeadLetterQueue(max_size=0)

    def test_full_dlq_drops_new(self) -> None:
        dlq = DeadLetterQueue(max_size=2)
        assert dlq.enqueue(_make_item(), reason="r", attempt=1) is True
        assert dlq.enqueue(_make_item(), reason="r", attempt=2) is True
        added = dlq.enqueue(_make_item(), reason="r", attempt=3)
        assert added is False
        assert dlq.size == 2

    def test_items_for_replay(self) -> None:
        dlq = DeadLetterQueue()
        a = _make_item()
        b = _make_item()
        dlq.enqueue(a, reason="x", attempt=1)
        dlq.enqueue(b, reason="y", attempt=2)
        replayed = dlq.items_for_replay()
        assert a in replayed
        assert b in replayed
        assert len(replayed) == 2


class TestDeadLetterPop:
    def test_pop_oldest_fifo(self) -> None:
        dlq = DeadLetterQueue()
        a = _make_item()
        b = _make_item()
        dlq.enqueue(a, reason="r1", attempt=1)
        dlq.enqueue(b, reason="r2", attempt=2)
        first = dlq.pop_oldest()
        assert first is not None
        assert first.item is a
        assert dlq.size == 1
        second = dlq.pop_oldest()
        assert second is not None
        assert second.item is b
        assert dlq.pop_oldest() is None


class TestDeadLetterDoesNotMutateItem:
    """The DLQ must not modify the WorkItem it stores."""

    def test_enqueue_does_not_change_item(self) -> None:
        item = _make_item()
        before = item
        dlq = DeadLetterQueue()
        dlq.enqueue(item, reason="x", attempt=1)
        # Item is the same frozen dataclass instance.
        assert item is before
        assert item.status == WorkItemStatus.FAILED