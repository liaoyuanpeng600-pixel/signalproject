from dataclasses import FrozenInstanceError

import pytest

from src.ingestion.models import (
    CollectionBatch,
    IngestionCheckpoint,
    RawDocument,
    RetryHint,
)


def _document(**overrides: object) -> RawDocument:
    values: dict[str, object] = {
        "id": "raw-1",
        "source_id": "source-1",
        "external_id": "external-1",
        "canonical_uri": "https://example.com/1",
        "published_at": "2026-07-25T00:00:00+00:00",
        "retrieved_at": "2026-07-25T01:00:00+00:00",
        "media_type": "text/plain",
        "content": "document",
        "content_hash": "sha256:" + "a" * 64,
        "connector_name": "fixture",
        "connector_version": "1.0.0",
    }
    values.update(overrides)
    return RawDocument(**values)  # type: ignore[arg-type]


def test_raw_document_is_frozen() -> None:
    document = _document()
    with pytest.raises(FrozenInstanceError):
        document.title = "changed"  # type: ignore[misc]


def test_raw_document_requires_content_or_reference() -> None:
    with pytest.raises(ValueError, match="content or raw_payload_ref"):
        _document(content=None)


def test_raw_document_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone"):
        _document(published_at="2026-07-25T00:00:00")


def test_collection_batch_rejects_duplicate_ids() -> None:
    document = _document()
    with pytest.raises(ValueError, match="duplicate"):
        CollectionBatch(records=(document, document))


def test_partial_batch_requires_retry_hint() -> None:
    with pytest.raises(ValueError, match="retry_hint"):
        CollectionBatch(records=(), is_partial=True)


def test_partial_batch_accepts_typed_retry_hint() -> None:
    batch = CollectionBatch(
        records=(),
        is_partial=True,
        retry_hint=RetryHint(retryable=True, retry_after_seconds=2.0),
    )
    assert batch.retry_hint is not None
    assert batch.retry_hint.retryable


def test_checkpoint_validates_revision_and_source() -> None:
    with pytest.raises(ValueError):
        IngestionCheckpoint(source_id="", connector_version="1.0.0")
    with pytest.raises(ValueError):
        IngestionCheckpoint(
            source_id="source-1", connector_version="1.0.0", revision=-1
        )
