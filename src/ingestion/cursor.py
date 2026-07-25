"""Persistence-neutral checkpoint contracts and an in-memory implementation."""

from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from src.core.ids import ID
from src.ingestion.models import IngestionCheckpoint


class CheckpointConflictError(Exception):
    """Raised when compare-and-set observes a stale checkpoint revision."""


class CursorStore(Protocol):
    def get(self, source_id: ID) -> IngestionCheckpoint | None:
        ...

    def compare_and_set(
        self,
        checkpoint: IngestionCheckpoint,
        *,
        expected_revision: int | None,
    ) -> IngestionCheckpoint:
        ...


class InMemoryCursorStore:
    """Thread-unsafe Phase 7.1 cursor store with future DB-compatible CAS."""

    def __init__(self) -> None:
        self._checkpoints: dict[str, IngestionCheckpoint] = {}

    def get(self, source_id: ID) -> IngestionCheckpoint | None:
        return self._checkpoints.get(str(source_id))

    def compare_and_set(
        self,
        checkpoint: IngestionCheckpoint,
        *,
        expected_revision: int | None,
    ) -> IngestionCheckpoint:
        key = str(checkpoint.source_id)
        current = self._checkpoints.get(key)
        if current is None:
            if expected_revision is not None:
                raise CheckpointConflictError(
                    f"Checkpoint {key!r} does not exist at revision "
                    f"{expected_revision}"
                )
            stored = replace(checkpoint, revision=0)
        else:
            if expected_revision != current.revision:
                raise CheckpointConflictError(
                    f"Checkpoint {key!r} is at revision {current.revision}, "
                    f"not {expected_revision}"
                )
            if checkpoint.connector_version != current.connector_version:
                raise CheckpointConflictError(
                    "Connector version change requires an explicit checkpoint migration"
                )
            stored = replace(checkpoint, revision=current.revision + 1)
        self._checkpoints[key] = stored
        return stored
