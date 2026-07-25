import pytest

from src.ingestion.deduplication import (
    collection_identity,
    content_hash,
    deduplicate_documents,
    normalize_content,
    raw_document_id,
)
from src.ingestion.models import RawDocument


def _document(identifier: str) -> RawDocument:
    return RawDocument(
        id=identifier,
        source_id="source",
        external_id=identifier,
        canonical_uri=f"https://example.com/{identifier}",
        published_at="2026-07-25T00:00:00+00:00",
        retrieved_at="2026-07-25T01:00:00+00:00",
        media_type="text/plain",
        content=identifier,
        content_hash=content_hash(identifier),
        connector_name="test",
        connector_version="1.0.0",
    )


def test_normalization_is_stable_across_newlines_and_trailing_space() -> None:
    assert normalize_content(" A  \r\nB\r\n") == "A\nB"


def test_content_hash_is_deterministic() -> None:
    assert content_hash("A\r\nB  ") == content_hash("A\nB")


def test_collection_identity_uses_source_and_external_id() -> None:
    assert collection_identity("s1", "item") != collection_identity("s2", "item")
    assert collection_identity("s1", " item ") == collection_identity("s1", "item")


def test_raw_document_id_is_deterministic() -> None:
    assert raw_document_id("s1", "item") == raw_document_id("s1", "item")
    assert raw_document_id("s1", "item").startswith("raw_")


def test_collection_identity_rejects_empty_input() -> None:
    with pytest.raises(ValueError):
        collection_identity("", "item")
    with pytest.raises(ValueError):
        collection_identity("source", " ")


def test_deduplicate_documents_handles_batch_and_known_identity() -> None:
    first = _document("raw-1")
    second = _document("raw-2")
    result = deduplicate_documents(
        (first, first, second),
        known_document_ids=frozenset({"raw-2"}),
    )
    assert result.accepted == (first,)
    assert result.duplicate_ids == ("raw-1", "raw-2")
