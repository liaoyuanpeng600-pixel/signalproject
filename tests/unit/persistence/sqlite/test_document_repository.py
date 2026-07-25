from __future__ import annotations

from dataclasses import replace

import pytest

from src.ingestion.models import RawDocument
from src.persistence.ingestion import (
    DocumentConflictError,
    DocumentInsertDisposition,
    DocumentRepository,
)
from src.persistence.sqlite import SQLiteDatabase, SQLiteDocumentRepository
from tests.contract.persistence.test_document_repository_contract import (
    DocumentRepositoryContract,
)
from tests.unit.persistence.sqlite.contracts import SQLiteContractTestMixin
from tests.unit.persistence.sqlite.factories import SQLiteTestDatabaseFactory


def _document(
    *,
    document_id: str = "raw-1",
    source_id: str = "source-1",
    external_id: str = "item-1",
    content: str | None = "bounded content",
    content_hash: str = f"sha256:{'a' * 64}",
    raw_payload_ref: str | None = None,
    provider_metadata: tuple[tuple[str, str], ...] = (),
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
        content=content,
        title="Document title",
        raw_payload_ref=raw_payload_ref,
        connector_name="fixture",
        connector_version="1.0.0",
        provider_metadata=provider_metadata,
    )


class TestSQLiteDocumentRepositoryContract(
    SQLiteContractTestMixin,
    DocumentRepositoryContract,
):
    def create_repository(self) -> DocumentRepository:
        return SQLiteDocumentRepository(self.database)


def test_first_insert_preserves_application_owned_id(
    sqlite_database: SQLiteDatabase,
) -> None:
    repository = SQLiteDocumentRepository(sqlite_database)
    document = _document(document_id="application-owned-id")

    result = repository.insert(document)

    assert result.disposition is DocumentInsertDisposition.INSERTED
    assert result.document.id == "application-owned-id"
    assert repository.get(document.id) == document


def test_equivalent_replay_returns_existing(
    sqlite_database: SQLiteDatabase,
) -> None:
    repository = SQLiteDocumentRepository(sqlite_database)
    document = _document()
    repository.insert(document)

    replay = repository.insert(document)

    assert replay.disposition is DocumentInsertDisposition.EXISTING
    assert replay.document == document


def test_same_collection_identity_with_different_id_resolves_canonical_document(
    sqlite_database: SQLiteDatabase,
) -> None:
    repository = SQLiteDocumentRepository(sqlite_database)
    canonical = _document(document_id="raw-canonical")
    repository.insert(canonical)

    replay = repository.insert(replace(canonical, id="raw-proposed"))

    assert replay.disposition is DocumentInsertDisposition.EXISTING
    assert replay.document == canonical
    assert replay.document.id == "raw-canonical"
    assert repository.get("raw-proposed") is None


def test_same_id_with_conflicting_collection_identity_raises(
    sqlite_database: SQLiteDatabase,
) -> None:
    repository = SQLiteDocumentRepository(sqlite_database)
    document = _document()
    repository.insert(document)

    with pytest.raises(DocumentConflictError):
        repository.insert(
            replace(
                document,
                external_id="item-2",
                canonical_uri="https://example.test/item-2",
            )
        )


def test_same_collection_identity_with_changed_content_raises(
    sqlite_database: SQLiteDatabase,
) -> None:
    repository = SQLiteDocumentRepository(sqlite_database)
    document = _document()
    repository.insert(document)

    with pytest.raises(DocumentConflictError):
        repository.insert(
            replace(
                document,
                content="changed content",
                content_hash=f"sha256:{'b' * 64}",
            )
        )


def test_same_collection_identity_with_changed_provenance_raises(
    sqlite_database: SQLiteDatabase,
) -> None:
    repository = SQLiteDocumentRepository(sqlite_database)
    document = _document()
    repository.insert(document)

    with pytest.raises(DocumentConflictError):
        repository.insert(
            replace(
                document,
                retrieved_at="2026-07-25T00:02:00+00:00",
            )
        )


def test_get_returns_document_by_application_id(
    sqlite_database: SQLiteDatabase,
) -> None:
    repository = SQLiteDocumentRepository(sqlite_database)
    document = _document()
    repository.insert(document)

    assert repository.get(document.id) == document


def test_find_by_collection_identity_returns_document(
    sqlite_database: SQLiteDatabase,
) -> None:
    repository = SQLiteDocumentRepository(sqlite_database)
    document = _document()
    repository.insert(document)

    assert repository.find_by_collection_identity(
        source_id=document.source_id,
        external_id=document.external_id,
    ) == document


def test_missing_lookups_return_none(sqlite_database: SQLiteDatabase) -> None:
    repository = SQLiteDocumentRepository(sqlite_database)

    assert repository.get("missing") is None
    assert repository.find_by_collection_identity(
        source_id="missing-source",
        external_id="missing-item",
    ) is None


def test_full_optional_fields_round_trip(
    sqlite_database: SQLiteDatabase,
) -> None:
    repository = SQLiteDocumentRepository(sqlite_database)
    document = _document(
        content=None,
        raw_payload_ref="payloads/raw-1.txt",
        provider_metadata=(("document_version", "2"), ("language", "en")),
    )

    result = repository.insert(document)

    assert result.document == document
    assert repository.get(document.id) == document


def test_provider_metadata_has_deterministic_round_trip_and_storage(
    sqlite_database: SQLiteDatabase,
) -> None:
    repository = SQLiteDocumentRepository(sqlite_database)
    document = _document(
        provider_metadata=(
            ("zeta", "last"),
            ("alpha", "second"),
            ("alpha", "first"),
        )
    )

    inserted = repository.insert(document)
    replay = repository.insert(
        replace(document, provider_metadata=tuple(reversed(document.provider_metadata)))
    )

    expected_metadata = (
        ("alpha", "first"),
        ("alpha", "second"),
        ("zeta", "last"),
    )
    assert inserted.document.provider_metadata == expected_metadata
    assert replay.disposition is DocumentInsertDisposition.EXISTING
    assert replay.document.provider_metadata == expected_metadata
    with sqlite_database.connection() as connection:
        stored_json = connection.execute(
            "SELECT provider_metadata_json FROM documents WHERE id = ?",
            (document.id,),
        ).fetchone()[0]
    assert stored_json == (
        '[["alpha","first"],["alpha","second"],["zeta","last"]]'
    )


def test_conflict_does_not_mutate_stored_document(
    sqlite_database: SQLiteDatabase,
) -> None:
    repository = SQLiteDocumentRepository(sqlite_database)
    document = _document()
    repository.insert(document)

    with pytest.raises(DocumentConflictError):
        repository.insert(
            replace(
                document,
                title="Rewritten title",
                connector_version="2.0.0",
            )
        )

    assert repository.get(document.id) == document


def test_repository_exposes_no_update_or_delete_api(
    sqlite_database: SQLiteDatabase,
) -> None:
    repository = SQLiteDocumentRepository(sqlite_database)

    assert not hasattr(repository, "update")
    assert not hasattr(repository, "delete")


def test_file_database_restart_preserves_documents(
    sqlite_database_factory: SQLiteTestDatabaseFactory,
) -> None:
    database = sqlite_database_factory.create()
    document = _document(
        provider_metadata=(("language", "en"),),
        raw_payload_ref="payloads/raw-1.txt",
    )
    SQLiteDocumentRepository(database).insert(document)

    restarted = sqlite_database_factory.reopen(database)
    repository = SQLiteDocumentRepository(restarted)

    assert repository.get(document.id) == document
    assert repository.find_by_collection_identity(
        source_id=document.source_id,
        external_id=document.external_id,
    ) == document
