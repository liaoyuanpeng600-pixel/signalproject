import pytest

from src.ingestion.cursor import CheckpointConflictError, InMemoryCursorStore
from src.ingestion.models import IngestionCheckpoint


def _checkpoint(
    *,
    source_id: str = "source-1",
    cursor: str | None = "cursor-1",
    version: str = "1.0.0",
) -> IngestionCheckpoint:
    return IngestionCheckpoint(
        source_id=source_id,
        cursor=cursor,
        connector_version=version,
    )


def test_create_and_get_checkpoint() -> None:
    store = InMemoryCursorStore()
    stored = store.compare_and_set(_checkpoint(), expected_revision=None)
    assert stored.revision == 0
    assert store.get("source-1") == stored


def test_update_increments_revision() -> None:
    store = InMemoryCursorStore()
    first = store.compare_and_set(_checkpoint(), expected_revision=None)
    second = store.compare_and_set(
        _checkpoint(cursor="cursor-2"), expected_revision=first.revision
    )
    assert second.revision == 1
    assert second.cursor == "cursor-2"


def test_stale_revision_conflicts() -> None:
    store = InMemoryCursorStore()
    store.compare_and_set(_checkpoint(), expected_revision=None)
    with pytest.raises(CheckpointConflictError):
        store.compare_and_set(_checkpoint(cursor="later"), expected_revision=9)


def test_connector_version_change_requires_migration() -> None:
    store = InMemoryCursorStore()
    first = store.compare_and_set(_checkpoint(), expected_revision=None)
    with pytest.raises(CheckpointConflictError, match="migration"):
        store.compare_and_set(
            _checkpoint(version="2.0.0"), expected_revision=first.revision
        )
