from dataclasses import replace

import pytest

from src.ingestion.models import RawDocument
from src.persistence.ingestion import (
    DocumentConflictError,
    DocumentInsertDisposition,
    DocumentRepository,
)


def _document(
    *,
    document_id: str = "raw-1",
    external_id: str = "item-1",
    content_hash: str = f"sha256:{'a' * 64}",
) -> RawDocument:
    return RawDocument(
        id=document_id,
        source_id="source-1",
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


class DocumentRepositoryContract:
    """Reusable behavioral suite for future persistence adapters."""

    def create_repository(self) -> DocumentRepository:
        raise NotImplementedError

    def test_first_insert_and_equivalent_replay(self) -> None:
        repository = self.create_repository()
        document = _document()

        first = repository.insert(document)
        replay = repository.insert(document)

        assert first.disposition is DocumentInsertDisposition.INSERTED
        assert replay.disposition is DocumentInsertDisposition.EXISTING
        assert replay.document == document

    def test_non_equivalent_authoritative_identity_conflicts(self) -> None:
        repository = self.create_repository()
        document = _document()
        repository.insert(document)

        with pytest.raises(DocumentConflictError):
            repository.insert(
                replace(
                    document,
                    content="changed",
                    content_hash=f"sha256:{'b' * 64}",
                )
            )

    def test_same_content_preserves_distinct_provenance(self) -> None:
        repository = self.create_repository()
        first = _document()
        second = _document(document_id="raw-2", external_id="item-2")

        repository.insert(first)
        repository.insert(second)

        assert repository.get(first.id) == first
        assert repository.get(second.id) == second
        assert first.content_hash == second.content_hash
