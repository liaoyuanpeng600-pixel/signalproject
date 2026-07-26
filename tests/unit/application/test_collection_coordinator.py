from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from src.application import CollectionCoordinator
from src.core.sources import Source, SourceType
from src.ingestion.models import (
    CollectionBatch,
    IngestionCheckpoint,
    RawDocument,
    RetryHint,
)
from src.ingestion.service import CollectionRunner
from src.persistence.ingestion import (
    CollectionCommitCommand,
    CollectionCommitResult,
    PersistenceOperationalError,
)


def _source() -> Source:
    return Source.create(
        type=SourceType.REGULATORY_FILING,
        url="file:///unused",
        name="Collection source",
        id="source-1",
    )


def _document() -> RawDocument:
    return RawDocument(
        id="raw-1",
        source_id="source-1",
        external_id="item-1",
        canonical_uri="https://example.test/item-1",
        published_at="2026-07-25T00:00:00+00:00",
        retrieved_at="2026-07-25T00:01:00+00:00",
        media_type="text/plain",
        content_hash=f"sha256:{'a' * 64}",
        content="bounded content",
        connector_name="recording",
        connector_version="1.0.0",
    )


class _CheckpointRepository:
    def __init__(
        self,
        checkpoint: IngestionCheckpoint | None,
        events: list[str],
    ) -> None:
        self.checkpoint = checkpoint
        self.events = events

    def get(self, source_id: str) -> IngestionCheckpoint | None:
        self.events.append("checkpoint.get")
        return self.checkpoint

    def compare_and_set(
        self,
        checkpoint: IngestionCheckpoint,
        *,
        expected_revision: int | None,
        connector_name: str,
    ) -> IngestionCheckpoint:
        raise AssertionError("coordinator must use the atomic collection port")


class _Connector:
    name = "recording"
    version = "1.0.0"

    def __init__(self, batch: CollectionBatch, events: list[str]) -> None:
        self.batch = batch
        self.events = events
        self.checkpoints: list[IngestionCheckpoint | None] = []

    def collect(
        self,
        source: Source,
        checkpoint: IngestionCheckpoint | None,
        limit: int,
    ) -> CollectionBatch:
        self.events.append("connector.collect")
        self.checkpoints.append(checkpoint)
        return self.batch


class _Persistence:
    def __init__(
        self,
        events: list[str],
        error: Exception | None = None,
    ) -> None:
        self.events = events
        self.error = error
        self.commands: list[CollectionCommitCommand] = []

    def commit_collection(
        self,
        command: CollectionCommitCommand,
    ) -> CollectionCommitResult:
        self.events.append("persistence.commit")
        self.commands.append(command)
        if self.error is not None:
            raise self.error
        revision = (
            0
            if command.expected_checkpoint_revision is None
            else command.expected_checkpoint_revision + 1
        )
        return CollectionCommitResult(
            documents_inserted=len(command.batch.records),
            documents_existing=0,
            document_work_created=len(command.document_work_items),
            document_work_existing=0,
            checkpoint=replace(command.next_checkpoint, revision=revision),
        )


def _coordinator(
    *,
    checkpoint: IngestionCheckpoint | None,
    events: list[str],
    persistence: _Persistence,
) -> CollectionCoordinator:
    return CollectionCoordinator(
        runner=CollectionRunner(),
        checkpoints=_CheckpointRepository(checkpoint, events),
        persistence=persistence,
    )


def test_collect_maps_one_complete_batch_to_one_atomic_command() -> None:
    events: list[str] = []
    checkpoint = IngestionCheckpoint(
        source_id="source-1",
        cursor="cursor-1",
        watermark="2026-07-24T00:00:00+00:00",
        last_success_at="2026-07-24T01:00:00+00:00",
        connector_version="1.0.0",
        revision=4,
    )
    batch = CollectionBatch(
        records=(_document(),),
        collected_at="2026-07-25T00:02:00+00:00",
        next_cursor="cursor-2",
    )
    connector = _Connector(batch, events)
    persistence = _Persistence(events)
    coordinator = _coordinator(
        checkpoint=checkpoint,
        events=events,
        persistence=persistence,
    )

    result = coordinator.collect(
        connector=connector,
        source=_source(),
        limit=25,
    )

    assert events == [
        "checkpoint.get",
        "connector.collect",
        "persistence.commit",
    ]
    assert connector.checkpoints == [checkpoint]
    assert len(persistence.commands) == 1
    command = persistence.commands[0]
    assert command.collection_work.checkpoint == checkpoint
    assert command.collection_work.limit == 25
    assert command.batch == batch
    assert command.expected_checkpoint_revision == checkpoint.revision
    assert command.next_checkpoint == IngestionCheckpoint(
        source_id="source-1",
        cursor="cursor-2",
        watermark=checkpoint.watermark,
        last_success_at=batch.collected_at,
        connector_version="1.0.0",
        revision=checkpoint.revision,
    )
    assert tuple(
        item.raw_document_id for item in command.document_work_items
    ) == ("raw-1",)
    assert result.checkpoint.revision == checkpoint.revision + 1


def test_none_next_cursor_preserves_existing_opaque_checkpoint_fields() -> None:
    events: list[str] = []
    checkpoint = IngestionCheckpoint(
        source_id="source-1",
        cursor="opaque-cursor",
        watermark="2026-07-24T00:00:00+00:00",
        last_success_at="2026-07-24T01:00:00+00:00",
        connector_version="1.0.0",
        revision=2,
    )
    batch = CollectionBatch(
        records=(),
        collected_at="2026-07-25T00:02:00+00:00",
    )
    persistence = _Persistence(events)
    coordinator = _coordinator(
        checkpoint=checkpoint,
        events=events,
        persistence=persistence,
    )

    coordinator.collect(
        connector=_Connector(batch, events),
        source=_source(),
    )

    proposed = persistence.commands[0].next_checkpoint
    assert proposed.cursor == checkpoint.cursor
    assert proposed.watermark == checkpoint.watermark
    assert proposed.last_success_at == batch.collected_at


def test_partial_batch_never_reaches_persistence() -> None:
    events: list[str] = []
    batch = CollectionBatch(
        records=(_document(),),
        is_partial=True,
        retry_hint=RetryHint(retryable=True),
    )
    persistence = _Persistence(events)
    coordinator = _coordinator(
        checkpoint=None,
        events=events,
        persistence=persistence,
    )

    with pytest.raises(ValueError, match="partial"):
        coordinator.collect(
            connector=_Connector(batch, events),
            source=_source(),
        )

    assert persistence.commands == []
    assert events == ["checkpoint.get", "connector.collect"]


def test_connector_failure_occurs_before_persistence() -> None:
    events: list[str] = []

    class FailingConnector(_Connector):
        def collect(
            self,
            source: Source,
            checkpoint: IngestionCheckpoint | None,
            limit: int,
        ) -> CollectionBatch:
            self.events.append("connector.collect")
            raise RuntimeError("connector failed")

    persistence = _Persistence(events)
    coordinator = _coordinator(
        checkpoint=None,
        events=events,
        persistence=persistence,
    )

    with pytest.raises(RuntimeError, match="connector failed"):
        coordinator.collect(
            connector=FailingConnector(CollectionBatch(records=()), events),
            source=_source(),
        )

    assert persistence.commands == []
    assert events == ["checkpoint.get", "connector.collect"]


def test_persistence_failure_is_not_retried_or_hidden() -> None:
    events: list[str] = []
    error = PersistenceOperationalError("injected failure")
    persistence = _Persistence(events, error=error)
    coordinator = _coordinator(
        checkpoint=None,
        events=events,
        persistence=persistence,
    )

    with pytest.raises(PersistenceOperationalError) as raised:
        coordinator.collect(
            connector=_Connector(
                CollectionBatch(records=(_document(),)),
                events,
            ),
            source=_source(),
        )

    assert raised.value is error
    assert len(persistence.commands) == 1


def test_application_coordinator_has_no_sqlite_dependency() -> None:
    source = (
        Path(__file__).parents[3]
        / "src"
        / "application"
        / "collection.py"
    ).read_text(encoding="utf-8")

    assert "sqlite3" not in source
    assert "src.persistence.sqlite" not in source
