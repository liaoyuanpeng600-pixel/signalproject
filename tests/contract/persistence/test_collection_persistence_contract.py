from src.ingestion.models import CollectionBatch, IngestionCheckpoint, RawDocument
from src.ingestion.work import CollectionWorkItem, DocumentProcessingWorkItem
from src.persistence.ingestion import (
    CollectionCommitCommand,
    CollectionCommitResult,
    CollectionPersistencePort,
)


def _command() -> CollectionCommitCommand:
    document = RawDocument(
        id="raw-1",
        source_id="source-1",
        external_id="item-1",
        canonical_uri="https://example.test/item-1",
        published_at="2026-07-25T00:00:00+00:00",
        retrieved_at="2026-07-25T00:01:00+00:00",
        media_type="text/plain",
        content_hash=f"sha256:{'a' * 64}",
        content="bounded content",
        connector_name="fixture",
        connector_version="1.0.0",
    )
    return CollectionCommitCommand(
        collection_work=CollectionWorkItem(
            id="work-collection",
            source_id="source-1",
            connector_name="fixture",
            connector_version="1.0.0",
            idempotency_key="collection:source-1",
        ),
        batch=CollectionBatch(records=(document,)),
        expected_checkpoint_revision=None,
        next_checkpoint=IngestionCheckpoint(
            source_id="source-1",
            cursor="fixture-v1:1",
            connector_version="1.0.0",
        ),
        document_work_items=(
            DocumentProcessingWorkItem(
                id="work-document",
                raw_document_id=document.id,
                idempotency_key="document:raw-1",
            ),
        ),
    )


class CollectionPersistenceContract:
    """Reusable atomic-boundary suite for future persistence adapters."""

    def create_port(self) -> CollectionPersistencePort:
        raise NotImplementedError

    def test_complete_collection_returns_one_summary(self) -> None:
        result = self.create_port().commit_collection(_command())

        assert isinstance(result, CollectionCommitResult)
        assert result.checkpoint.source_id == "source-1"
