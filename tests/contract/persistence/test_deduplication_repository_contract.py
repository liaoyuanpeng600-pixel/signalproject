import pytest

from src.persistence.ingestion import (
    DeduplicationIdentity,
    DeduplicationRepository,
    IdentityConflictError,
    IdentityInsertDisposition,
    IdentityKind,
)


class DeduplicationRepositoryContract:
    """Reusable identity-claim suite for future persistence adapters."""

    def create_repository(self) -> DeduplicationRepository:
        raise NotImplementedError

    def test_collection_identity_is_idempotently_unique(self) -> None:
        repository = self.create_repository()
        claim = DeduplicationIdentity(
            IdentityKind.COLLECTION,
            "collection-key",
            "collection-v1",
            "raw-1",
        )

        first = repository.insert_identity(claim)
        replay = repository.insert_identity(claim)

        assert first.disposition is IdentityInsertDisposition.INSERTED
        assert replay.disposition is IdentityInsertDisposition.EXISTING
        assert replay.document_ids == ("raw-1",)

    def test_collection_identity_cannot_be_reassigned(self) -> None:
        repository = self.create_repository()
        repository.insert_identity(
            DeduplicationIdentity(
                IdentityKind.COLLECTION,
                "collection-key",
                "collection-v1",
                "raw-1",
            )
        )

        with pytest.raises(IdentityConflictError):
            repository.insert_identity(
                DeduplicationIdentity(
                    IdentityKind.COLLECTION,
                    "collection-key",
                    "collection-v1",
                    "raw-2",
                )
            )

    def test_content_identity_maps_to_multiple_documents(self) -> None:
        repository = self.create_repository()
        for document_id in ("raw-2", "raw-1"):
            repository.insert_identity(
                DeduplicationIdentity(
                    IdentityKind.CONTENT,
                    f"sha256:{'a' * 64}",
                    "text-v1",
                    document_id,
                )
            )

        assert repository.resolve(
            identity_kind=IdentityKind.CONTENT,
            identity_key=f"sha256:{'a' * 64}",
            identity_version="text-v1",
        ) == ("raw-1", "raw-2")
