import pytest

from src.ingestion.models import IngestionCheckpoint
from src.ingestion.work import (
    CollectionWorkItem,
    DocumentProcessingWorkItem,
    ResearchWorkItem,
)


def test_collection_work_item_creation() -> None:
    checkpoint = IngestionCheckpoint(
        source_id="source-1", connector_version="1.0.0"
    )
    item = CollectionWorkItem(
        source_id="source-1",
        connector_name="test",
        connector_version="1.0.0",
        checkpoint=checkpoint,
        idempotency_key="collect:source-1:0",
        limit=25,
    )
    assert item.source_id == "source-1"
    assert item.limit == 25
    assert item.id


def test_collection_work_rejects_foreign_checkpoint() -> None:
    checkpoint = IngestionCheckpoint(
        source_id="source-2", connector_version="1.0.0"
    )
    with pytest.raises(ValueError, match="another Source"):
        CollectionWorkItem(
            source_id="source-1",
            connector_name="test",
            connector_version="1.0.0",
            checkpoint=checkpoint,
            idempotency_key="collect",
        )


def test_document_processing_work_item_creation() -> None:
    item = DocumentProcessingWorkItem(
        raw_document_id="raw-1", idempotency_key="document:raw-1"
    )
    assert item.raw_document_id == "raw-1"


def test_research_work_item_is_typed() -> None:
    item = ResearchWorkItem(
        entity_id="entity-1",
        signal_ids=("signal-1", "signal-2"),
        topic_key="earnings",
        idempotency_key="research:entity-1:earnings",
    )
    assert item.signal_ids == ("signal-1", "signal-2")


def test_research_work_item_rejects_duplicate_signals() -> None:
    with pytest.raises(ValueError, match="unique"):
        ResearchWorkItem(
            entity_id="entity-1",
            signal_ids=("signal-1", "signal-1"),
            topic_key="earnings",
            idempotency_key="research",
        )
