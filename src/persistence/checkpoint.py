"""
Checkpoint — snapshot and restore of an InMemoryStore.

A checkpoint captures the full state of an InMemoryStore as a JSON-serializable
dict. Checkpoints are the MVP's mechanism for persisting between sessions and
for replaying cycles in tests.

For the MVP, checkpoints are in-memory only. Production checkpoints (writing
to disk, replaying across processes) come post-MVP.

This module is a thin layer on top of `InMemoryStore.snapshot()` and
`InMemoryStore.restore()`. It exists so that future checkpoint features
(e.g., compression, hashing, signed checkpoints) have a stable entry point.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.persistence.store import Store


def checkpoint(store: "Store") -> dict[str, object]:
    """Capture a snapshot of the store's current state.

    Returns:
        A JSON-serializable dict suitable for persistence to disk or
        transmission across processes.
    """
    return store.snapshot()


def restore(store: "Store", snapshot: dict[str, object]) -> None:
    """Replace the store's contents with the given snapshot.

    The store is cleared before loading. Snapshots produced by `checkpoint()`
    are guaranteed to round-trip; snapshots from other sources should be
    validated.
    """
    store.restore(snapshot)