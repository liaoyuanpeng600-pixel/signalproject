from __future__ import annotations

import pytest

from src.persistence.ingestion import (
    DeduplicationIdentity,
    DeduplicationRepository,
    IdentityConflictError,
    IdentityInsertDisposition,
    IdentityKind,
)
from src.persistence.sqlite import (
    SQLiteDeduplicationRepository,
)
from tests.contract.persistence.test_deduplication_repository_contract import (
    DeduplicationRepositoryContract,
)
from tests.unit.persistence.sqlite.contracts import (
    SQLiteIdentityContractTestMixin,
)
from tests.unit.persistence.sqlite.factories import SQLiteTestDatabaseFactory


def _identity(
    *,
    identity_kind: IdentityKind = IdentityKind.COLLECTION,
    identity_key: str = "source-1:item-1",
    identity_version: str = "collection-v1",
    document_id: str = "raw-1",
) -> DeduplicationIdentity:
    return DeduplicationIdentity(
        identity_kind=identity_kind,
        identity_key=identity_key,
        identity_version=identity_version,
        document_id=document_id,
    )


class TestSQLiteDeduplicationRepositoryContract(
    SQLiteIdentityContractTestMixin,
    DeduplicationRepositoryContract,
):
    def create_repository(self) -> DeduplicationRepository:
        return SQLiteDeduplicationRepository(self.database)


class TestSQLiteDeduplicationRepository(SQLiteIdentityContractTestMixin):
    @pytest.fixture
    def repository(self) -> SQLiteDeduplicationRepository:
        return SQLiteDeduplicationRepository(self.database)

    def test_first_insert_returns_inserted_mapping(
        self,
        repository: SQLiteDeduplicationRepository,
    ) -> None:
        result = repository.insert_identity(_identity())

        assert result.disposition is IdentityInsertDisposition.INSERTED
        assert result.document_ids == ("raw-1",)

    def test_missing_resolve_returns_empty_tuple(
        self,
        repository: SQLiteDeduplicationRepository,
    ) -> None:
        assert repository.resolve(
            identity_kind=IdentityKind.COLLECTION,
            identity_key="missing",
            identity_version="collection-v1",
        ) == ()

    def test_equivalent_collection_replay_returns_existing(
        self,
        repository: SQLiteDeduplicationRepository,
    ) -> None:
        identity = _identity()
        repository.insert_identity(identity)

        result = repository.insert_identity(identity)

        assert result.disposition is IdentityInsertDisposition.EXISTING
        assert result.document_ids == ("raw-1",)

    def test_collection_reassignment_conflicts_without_mutation(
        self,
        repository: SQLiteDeduplicationRepository,
    ) -> None:
        repository.insert_identity(_identity())

        with pytest.raises(IdentityConflictError):
            repository.insert_identity(_identity(document_id="raw-2"))

        assert repository.resolve(
            identity_kind=IdentityKind.COLLECTION,
            identity_key="source-1:item-1",
            identity_version="collection-v1",
        ) == ("raw-1",)

    @pytest.mark.parametrize(
        "identity_kind,identity_key,identity_version",
        [
            (
                IdentityKind.COLLECTION,
                "source-1:item-1",
                "collection-v1",
            ),
            (
                IdentityKind.CONTENT,
                f"sha256:{'a' * 64}",
                "text-v1",
            ),
        ],
    )
    def test_same_identity_and_document_with_different_version_conflicts(
        self,
        repository: SQLiteDeduplicationRepository,
        identity_kind: IdentityKind,
        identity_key: str,
        identity_version: str,
    ) -> None:
        repository.insert_identity(
            _identity(
                identity_kind=identity_kind,
                identity_key=identity_key,
                identity_version=identity_version,
            )
        )

        with pytest.raises(IdentityConflictError):
            repository.insert_identity(
                _identity(
                    identity_kind=identity_kind,
                    identity_key=identity_key,
                    identity_version=f"{identity_version}-changed",
                )
            )

        assert repository.resolve(
            identity_kind=identity_kind,
            identity_key=identity_key,
            identity_version=identity_version,
        ) == ("raw-1",)
        assert repository.resolve(
            identity_kind=identity_kind,
            identity_key=identity_key,
            identity_version=f"{identity_version}-changed",
        ) == ()

    def test_content_identity_maps_to_multiple_documents_in_sorted_order(
        self,
        repository: SQLiteDeduplicationRepository,
    ) -> None:
        key = f"sha256:{'b' * 64}"
        for document_id in ("raw-2", "raw-1"):
            result = repository.insert_identity(
                _identity(
                    identity_kind=IdentityKind.CONTENT,
                    identity_key=key,
                    identity_version="text-v1",
                    document_id=document_id,
                )
            )

        assert result.disposition is IdentityInsertDisposition.INSERTED
        assert result.document_ids == ("raw-1", "raw-2")
        assert repository.resolve(
            identity_kind=IdentityKind.CONTENT,
            identity_key=key,
            identity_version="text-v1",
        ) == ("raw-1", "raw-2")

    def test_content_replay_returns_all_existing_mappings(
        self,
        repository: SQLiteDeduplicationRepository,
    ) -> None:
        key = f"sha256:{'c' * 64}"
        raw_1 = _identity(
            identity_kind=IdentityKind.CONTENT,
            identity_key=key,
            identity_version="text-v1",
        )
        raw_2 = _identity(
            identity_kind=IdentityKind.CONTENT,
            identity_key=key,
            identity_version="text-v1",
            document_id="raw-2",
        )
        repository.insert_identity(raw_1)
        repository.insert_identity(raw_2)

        replay = repository.insert_identity(raw_1)

        assert replay.disposition is IdentityInsertDisposition.EXISTING
        assert replay.document_ids == ("raw-1", "raw-2")

    def test_identity_kinds_remain_independent(
        self,
        repository: SQLiteDeduplicationRepository,
    ) -> None:
        key = "shared-key"
        repository.insert_identity(
            _identity(
                identity_kind=IdentityKind.COLLECTION,
                identity_key=key,
                identity_version="v1",
            )
        )
        repository.insert_identity(
            _identity(
                identity_kind=IdentityKind.CONTENT,
                identity_key=key,
                identity_version="v1",
                document_id="raw-2",
            )
        )

        assert repository.resolve(
            identity_kind=IdentityKind.COLLECTION,
            identity_key=key,
            identity_version="v1",
        ) == ("raw-1",)
        assert repository.resolve(
            identity_kind=IdentityKind.CONTENT,
            identity_key=key,
            identity_version="v1",
        ) == ("raw-2",)

    def test_row_mapping_preserves_all_identity_fields(
        self,
        repository: SQLiteDeduplicationRepository,
    ) -> None:
        identity = _identity(
            identity_kind=IdentityKind.CONTENT,
            identity_key=f"sha256:{'d' * 64}",
            identity_version="normalized-text-v2",
            document_id="raw-2",
        )
        repository.insert_identity(identity)

        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT identity_kind, identity_key, identity_version,
                       document_id, created_at
                FROM deduplication_identities
                """
            ).fetchone()

        assert tuple(row) == (
            identity.identity_kind.value,
            identity.identity_key,
            identity.identity_version,
            identity.document_id,
            row["created_at"],
        )
        assert row["created_at"]

    def test_unknown_document_binding_is_rejected(
        self,
        repository: SQLiteDeduplicationRepository,
    ) -> None:
        identity = _identity(document_id="missing-document")

        with pytest.raises(IdentityConflictError):
            repository.insert_identity(identity)

        assert repository.resolve(
            identity_kind=identity.identity_kind,
            identity_key=identity.identity_key,
            identity_version=identity.identity_version,
        ) == ()

    def test_file_database_restart_preserves_identity_mappings(
        self,
        repository: SQLiteDeduplicationRepository,
    ) -> None:
        identity = _identity(
            identity_kind=IdentityKind.CONTENT,
            identity_key=f"sha256:{'e' * 64}",
            identity_version="text-v1",
        )
        repository.insert_identity(identity)

        restarted = SQLiteTestDatabaseFactory.reopen(self.database)
        restarted_repository = SQLiteDeduplicationRepository(restarted)

        assert restarted_repository.resolve(
            identity_kind=identity.identity_kind,
            identity_key=identity.identity_key,
            identity_version=identity.identity_version,
        ) == ("raw-1",)
