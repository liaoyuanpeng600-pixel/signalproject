from dataclasses import FrozenInstanceError

import pytest

from src.ingestion.models import (
    CollectionBatch,
    IngestionCheckpoint,
    RawDocument,
    RetryHint,
)
from src.ingestion.work import (
    CollectionWorkItem,
    DocumentProcessingWorkItem,
)
from src.persistence.ingestion.models import (
    CollectionCommitCommand,
    CollectionCommitResult,
    DeduplicationIdentity,
    DocumentInsertDisposition,
    DocumentInsertResult,
    IdentityInsertDisposition,
    IdentityInsertResult,
    IdentityKind,
    WorkInsertDisposition,
    WorkInsertResult,
)


def _document(
    *,
    document_id: str = "raw-1",
    source_id: str = "source-1",
    external_id: str = "item-1",
    content_hash: str = f"sha256:{'a' * 64}",
) -> RawDocument:
    return RawDocument(
        id=document_id,
        source_id=source_id,
        external_id=external_id,
        canonical_uri=f"https://example.test/{external_id}",
        published_at="2026-07-25T00:00:00+00:00",
        retrieved_at="2026-07-25T00:01:00+00:00",
        media_type="text/plain",
        content_hash=content_hash,
        content="bounded content",
        connector_name="fixture",
        connector_version="1.0.0",
    )


def _command(*, batch: CollectionBatch | None = None) -> CollectionCommitCommand:
    document = _document()
    selected_batch = batch or CollectionBatch(records=(document,))
    collection_work = CollectionWorkItem(
        id="work-collection",
        source_id="source-1",
        connector_name="fixture",
        connector_version="1.0.0",
        idempotency_key="collection:source-1",
    )
    document_work = tuple(
        DocumentProcessingWorkItem(
            id=f"work-{record.id}",
            raw_document_id=record.id,
            idempotency_key=f"document:{record.id}",
        )
        for record in selected_batch.records
    )
    return CollectionCommitCommand(
        collection_work=collection_work,
        batch=selected_batch,
        expected_checkpoint_revision=None,
        next_checkpoint=IngestionCheckpoint(
            source_id="source-1",
            cursor="fixture-v1:1",
            connector_version="1.0.0",
        ),
        document_work_items=document_work,
    )


def test_result_dtos_are_immutable_and_use_explicit_dispositions() -> None:
    document_result = DocumentInsertResult(
        document=_document(),
        disposition=DocumentInsertDisposition.INSERTED,
    )
    work_result = WorkInsertResult(
        work_item=DocumentProcessingWorkItem(
            id="work-1",
            raw_document_id="raw-1",
            idempotency_key="document:raw-1",
        ),
        disposition=WorkInsertDisposition.EXISTING,
    )

    with pytest.raises(FrozenInstanceError):
        document_result.disposition = DocumentInsertDisposition.EXISTING  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        work_result.disposition = WorkInsertDisposition.INSERTED  # type: ignore[misc]


def test_identity_result_has_unique_deterministic_document_order() -> None:
    result = IdentityInsertResult(
        disposition=IdentityInsertDisposition.EXISTING,
        document_ids=("raw-2", "raw-1"),
    )

    assert result.document_ids == ("raw-1", "raw-2")
    with pytest.raises(ValueError, match="unique"):
        IdentityInsertResult(
            disposition=IdentityInsertDisposition.EXISTING,
            document_ids=("raw-1", "raw-1"),
        )


def test_identity_claim_keeps_collection_and_content_semantics_explicit() -> None:
    collection_claim = DeduplicationIdentity(
        identity_kind=IdentityKind.COLLECTION,
        identity_key="collection-key",
        identity_version="collection-v1",
        document_id="raw-1",
    )
    content_claim = DeduplicationIdentity(
        identity_kind=IdentityKind.CONTENT,
        identity_key=f"sha256:{'a' * 64}",
        identity_version="text-v1",
        document_id="raw-2",
    )

    assert collection_claim.identity_kind is IdentityKind.COLLECTION
    assert content_claim.identity_kind is IdentityKind.CONTENT


def test_collection_command_rejects_partial_batch() -> None:
    partial = CollectionBatch(
        records=(_document(),),
        is_partial=True,
        retry_hint=RetryHint(retryable=True),
    )

    with pytest.raises(ValueError, match="partial"):
        _command(batch=partial)


def test_collection_command_allows_work_for_deduplicated_batch_subset() -> None:
    command = _command()

    subset = CollectionCommitCommand(
        collection_work=command.collection_work,
        batch=command.batch,
        expected_checkpoint_revision=None,
        next_checkpoint=command.next_checkpoint,
        document_work_items=(),
    )

    assert subset.document_work_items == ()


def test_collection_command_rejects_work_outside_batch() -> None:
    command = _command()

    with pytest.raises(ValueError, match="documents in the batch"):
        CollectionCommitCommand(
            collection_work=command.collection_work,
            batch=command.batch,
            expected_checkpoint_revision=None,
            next_checkpoint=command.next_checkpoint,
            document_work_items=(
                DocumentProcessingWorkItem(
                    id="work-other",
                    raw_document_id="raw-other",
                    idempotency_key="document:raw-other",
                ),
            ),
        )


def test_collection_command_rejects_non_document_work() -> None:
    command = _command()

    with pytest.raises(TypeError, match="DocumentProcessingWorkItem"):
        CollectionCommitCommand(
            collection_work=command.collection_work,
            batch=command.batch,
            expected_checkpoint_revision=None,
            next_checkpoint=command.next_checkpoint,
            document_work_items=(command.collection_work,),  # type: ignore[arg-type]
        )


def test_collection_result_rejects_negative_or_boolean_counts() -> None:
    checkpoint = _command().next_checkpoint

    with pytest.raises(ValueError, match="documents_inserted"):
        CollectionCommitResult(-1, 0, 0, 0, checkpoint)
    with pytest.raises(ValueError, match="documents_inserted"):
        CollectionCommitResult(True, 0, 0, 0, checkpoint)  # type: ignore[arg-type]


def test_collection_result_exposes_only_counts_and_checkpoint() -> None:
    result = CollectionCommitResult(
        documents_inserted=1,
        documents_existing=0,
        document_work_created=1,
        document_work_existing=0,
        checkpoint=_command().next_checkpoint,
    )

    assert result.documents_inserted == 1
    assert result.checkpoint.source_id == "source-1"
    assert not hasattr(result, "connection")
    assert not hasattr(result, "rows")
