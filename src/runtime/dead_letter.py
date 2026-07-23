"""
DeadLetterQueue — Phase 3 Checkpoint 4.

A DeadLetterQueue (DLQ) holds WorkItems that exhausted their retry budget
or are non-retryable by policy. The DLQ is an MVP abstraction: items are
stored in-process. A production DLQ would persist via the `Store` interface.

The DLQ does NOT mutate WorkItem status. Items entering the DLQ remain in
their pre-DLQ state (typically FAILED). Operators inspect the DLQ and may
choose to re-enqueue manually — this is the MANUAL policy's canonical
path.

Dependency rules:
- DLQ MUST NOT import any concrete persistence backend.
- DLQ MUST NOT modify the WorkItem (it stores references).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.runtime.queue import WorkItem


@dataclass(frozen=True, slots=True)
class DeadLetterEntry:
    """A WorkItem in the DLQ plus the reason it was dead-lettered."""

    item: "WorkItem"
    reason: str
    attempt: int
    dead_lettered_at: str


class DeadLetterQueue:
    """In-process DLQ for failed WorkItems.

    Bounded by `max_size`. When full, new entries are dropped (FIFO eviction
    is a post-MVP enhancement; the MVP chooses drop-newest to avoid silent
    overwrites).
    """

    def __init__(self, max_size: int | None = None) -> None:
        if max_size is not None and max_size <= 0:
            raise ValueError("max_size must be positive or None")
        self._entries: deque[DeadLetterEntry] = deque()
        self._max_size = max_size

    @property
    def size(self) -> int:
        return len(self._entries)

    @property
    def max_size(self) -> int | None:
        return self._max_size

    def enqueue(self, item: "WorkItem", *, reason: str, attempt: int) -> bool:
        """Add a failed WorkItem to the DLQ.

        Returns:
            True if the entry was added; False if the DLQ is full and the
            entry was dropped (drop-newest).
        """
        from src.core.timestamps import now_utc

        if self._max_size is not None and self.size >= self._max_size:
            return False
        self._entries.append(
            DeadLetterEntry(
                item=item,
                reason=reason,
                attempt=attempt,
                dead_lettered_at=now_utc(),
            )
        )
        return True

    def list_entries(self) -> tuple[DeadLetterEntry, ...]:
        return tuple(self._entries)

    def pop_oldest(self) -> DeadLetterEntry | None:
        """Remove and return the oldest DLQ entry, or None if empty."""
        if not self._entries:
            return None
        return self._entries.popleft()

    def clear(self) -> None:
        self._entries.clear()

    def items_for_replay(self) -> tuple["WorkItem", ...]:
        """Return the WorkItems in the DLQ (without metadata), for manual replay."""
        return tuple(entry.item for entry in self._entries)


__all__ = ["DeadLetterEntry", "DeadLetterQueue"]