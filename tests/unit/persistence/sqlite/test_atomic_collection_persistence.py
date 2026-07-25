from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Iterator

import pytest

import src.persistence.sqlite.atomic as atomic_module
from src.ingestion.deduplication import (
    IDENTITY_VERSION,
    NORMALIZATION_VERSION,
    collection_identity,
)
from src.ingestion.models import CollectionBatch, IngestionCheckpoint, RawDocument
from src.ingestion.work import CollectionWorkItem, DocumentProcessingWorkItem
from src.persistence.ingestion import (
    CheckpointConflictError,
    CollectionCommitCommand,
    CollectionPersistencePort,
    DocumentConflictError,
    IdentityConflictError,
    IdentityKind,
    PersistenceOperationalError,
    WorkItemConflictError,
)
from src.persistence.sqlite import (
    SQLiteAtomicCollectionPersistence,
    SQLiteCheckpointRepository,
    SQLiteDatabase,
    SQLiteDeduplicationRepository,
    SQLiteDocumentRepository,
    SQLiteWorkItemRepository,
)
from tests.contract.persistence.test_collection_persistence_contract import (
    CollectionPersistenceContract,
)
from tests.unit.persistence.sqlite.contracts import SQLiteContractTestMixin
from tests.unit.persistence.sqlite.factories import SQLiteTestDatabaseFactory


def _document(
    number: int = 1,
    *,
    content: str | None = None,
) -> RawDocument:
    digest_character = format(number, "x")
    return RawDocument(
        id=f"raw-{number}",
        source_id="source-1",
        external_id=f"item-{number}",
        canonical_uri=f"https://example.test/item-{number}",
        published_at="2026-07-25T00:00:00+00:00",
        retrieved_at="2026-07-25T00:01:00+00:00",
        media_type="text/plain",
        content_hash=f"sha256:{digest_character * 64}",
        content=content or f"bounded content {number}",
        connector_name="fixture",
        connector_version="1.0.0",
    )


def _document_work(document: RawDocument) -> DocumentProcessingWorkItem:
    return DocumentProcessingWorkItem(
        id=f"work-{document.id}",
        raw_document_id=document.id,
        idempotency_key=f"document:{document.id}",
        created_at="2026-07-25T00:02:00+00:00",
    )


def _command(
    *,
    documents: tuple[RawDocument, ...] | None = None,
    work_documents: tuple[RawDocument, ...] | None = None,
    current_checkpoint: IngestionCheckpoint | None = None,
    expected_revision: int | None = None,
    next_cursor: str = "fixture-v1:1",
    connector_name: str = "fixture",
) -> CollectionCommitCommand:
    records = documents if documents is not None else (_document(),)
    selected = work_documents if work_documents is not None else records
    return CollectionCommitCommand(
        collection_work=CollectionWorkItem(
            id="work-collection",
            source_id="source-1",
            connector_name=connector_name,
            connector_version="1.0.0",
            idempotency_key="collection:source-1",
            checkpoint=current_checkpoint,
            created_at="2026-07-25T00:02:00+00:00",
        ),
        batch=CollectionBatch(
            records=records,
            collected_at="2026-07-25T00:02:00+00:00",
        ),
        expected_checkpoint_revision=expected_revision,
        next_checkpoint=IngestionCheckpoint(
            source_id="source-1",
            cursor=next_cursor,
            connector_version="1.0.0",
        ),
        document_work_items=tuple(_document_work(document) for document in selected),
    )


def _table_count(database: SQLiteDatabase, table: str) -> int:
    with database.connection() as connection:
        return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


class TestSQLiteAtomicCollectionPersistenceContract(
    SQLiteContractTestMixin,
    CollectionPersistenceContract,
):
    def create_port(self) -> CollectionPersistencePort:
        return SQLiteAtomicCollectionPersistence(self.database)


class TestSQLiteAtomicCollectionPersistence(SQLiteContractTestMixin):
    @pytest.fixture
    def port(self) -> SQLiteAtomicCollectionPersistence:
        return SQLiteAtomicCollectionPersistence(self.database)

    def test_successful_atomic_persistence(
        self,
        port: SQLiteAtomicCollectionPersistence,
    ) -> None:
        document = _document()
        result = port.commit_collection(_command())

        assert result.documents_inserted == 1
        assert result.documents_existing == 0
        assert result.document_work_created == 1
        assert result.document_work_existing == 0
        assert result.checkpoint.revision == 0
        assert SQLiteDocumentRepository(self.database).get(document.id) == document
        assert SQLiteWorkItemRepository(self.database).get(
            f"work-{document.id}"
        ) == _document_work(document)

        identities = SQLiteDeduplicationRepository(self.database)
        assert identities.resolve(
            identity_kind=IdentityKind.COLLECTION,
            identity_key=collection_identity(
                document.source_id,
                document.external_id,
            ),
            identity_version=IDENTITY_VERSION,
        ) == (document.id,)
        assert identities.resolve(
            identity_kind=IdentityKind.CONTENT,
            identity_key=document.content_hash,
            identity_version=NORMALIZATION_VERSION,
        ) == (document.id,)

    def test_multiple_documents_commit_together(
        self,
        port: SQLiteAtomicCollectionPersistence,
    ) -> None:
        documents = (_document(1), _document(2))

        result = port.commit_collection(_command(documents=documents))

        assert result.documents_inserted == 2
        assert result.document_work_created == 2
        assert _table_count(self.database, "documents") == 2
        assert _table_count(self.database, "deduplication_identities") == 4
        assert _table_count(self.database, "work_items") == 2

    def test_document_work_may_cover_only_a_subset(
        self,
        port: SQLiteAtomicCollectionPersistence,
    ) -> None:
        documents = (_document(1), _document(2))

        result = port.commit_collection(
            _command(
                documents=documents,
                work_documents=(documents[1],),
            )
        )

        assert result.documents_inserted == 2
        assert result.document_work_created == 1
        repository = SQLiteWorkItemRepository(self.database)
        assert repository.get("work-raw-1") is None
        assert repository.get("work-raw-2") == _document_work(documents[1])

    def test_empty_complete_batch_advances_checkpoint_only(
        self,
        port: SQLiteAtomicCollectionPersistence,
    ) -> None:
        result = port.commit_collection(
            _command(documents=(), work_documents=())
        )

        assert result.documents_inserted == 0
        assert result.documents_existing == 0
        assert result.document_work_created == 0
        assert result.document_work_existing == 0
        assert result.checkpoint.revision == 0
        assert _table_count(self.database, "documents") == 0
        assert _table_count(self.database, "work_items") == 0

    def test_canonical_replay_returns_existing_counts(
        self,
        port: SQLiteAtomicCollectionPersistence,
    ) -> None:
        command = _command()
        first = port.commit_collection(command)
        replay = _command(
            current_checkpoint=first.checkpoint,
            expected_revision=first.checkpoint.revision,
            next_cursor="fixture-v1:1",
        )

        result = port.commit_collection(replay)

        assert result.documents_inserted == 0
        assert result.documents_existing == 1
        assert result.document_work_created == 0
        assert result.document_work_existing == 1
        assert result.checkpoint.revision == 1
        assert _table_count(self.database, "documents") == 1
        assert _table_count(self.database, "deduplication_identities") == 2
        assert _table_count(self.database, "work_items") == 1

    def test_exact_initial_command_replay_conflicts_at_frozen_cas_boundary(
        self,
        port: SQLiteAtomicCollectionPersistence,
    ) -> None:
        command = _command()
        committed = port.commit_collection(command)

        with pytest.raises(CheckpointConflictError):
            port.commit_collection(command)

        assert _table_count(self.database, "documents") == 1
        assert _table_count(self.database, "deduplication_identities") == 2
        assert _table_count(self.database, "work_items") == 1
        assert (
            SQLiteCheckpointRepository(self.database).get("source-1")
            == committed.checkpoint
        )

    def test_document_conflict_rolls_back_checkpoint(
        self,
        port: SQLiteAtomicCollectionPersistence,
    ) -> None:
        original = _document()
        SQLiteDocumentRepository(self.database).insert(original)
        conflicting = replace(
            original,
            content="changed",
            content_hash=f"sha256:{'f' * 64}",
        )

        with pytest.raises(DocumentConflictError):
            port.commit_collection(
                _command(
                    documents=(conflicting,),
                    work_documents=(),
                )
            )

        assert SQLiteDocumentRepository(self.database).get(original.id) == original
        assert SQLiteCheckpointRepository(self.database).get("source-1") is None

    def test_collection_identity_conflict_rolls_back_new_document(
        self,
        port: SQLiteAtomicCollectionPersistence,
    ) -> None:
        owner = replace(
            _document(9),
            source_id="source-other",
            external_id="owner-item",
        )
        SQLiteDocumentRepository(self.database).insert(owner)
        SQLiteDeduplicationRepository(self.database).insert_identity(
            atomic_module.DeduplicationIdentity(
                identity_kind=IdentityKind.COLLECTION,
                identity_key=collection_identity("source-1", "item-1"),
                identity_version=IDENTITY_VERSION,
                document_id=owner.id,
            )
        )

        with pytest.raises(IdentityConflictError):
            port.commit_collection(_command())

        assert SQLiteDocumentRepository(self.database).get("raw-1") is None
        assert SQLiteCheckpointRepository(self.database).get("source-1") is None

    def test_work_item_conflict_rolls_back_documents_and_identities(
        self,
        port: SQLiteAtomicCollectionPersistence,
    ) -> None:
        SQLiteWorkItemRepository(self.database).insert(
            _document_work(_document(2))
        )
        command = _command()
        conflicting_work = replace(
            command.document_work_items[0],
            idempotency_key="document:raw-2",
        )
        command = replace(
            command,
            document_work_items=(conflicting_work,),
        )

        with pytest.raises(WorkItemConflictError):
            port.commit_collection(command)

        assert SQLiteDocumentRepository(self.database).get("raw-1") is None
        assert _table_count(self.database, "deduplication_identities") == 0
        assert _table_count(self.database, "work_items") == 1

    def test_stale_checkpoint_rolls_back_all_intermediate_effects(
        self,
        port: SQLiteAtomicCollectionPersistence,
    ) -> None:
        checkpoints = SQLiteCheckpointRepository(self.database)
        initial = checkpoints.compare_and_set(
            IngestionCheckpoint(
                source_id="source-1",
                cursor="cursor-0",
                connector_version="1.0.0",
            ),
            expected_revision=None,
            connector_name="fixture",
        )
        checkpoints.compare_and_set(
            replace(initial, cursor="cursor-1"),
            expected_revision=initial.revision,
            connector_name="fixture",
        )

        with pytest.raises(CheckpointConflictError):
            port.commit_collection(
                _command(
                    current_checkpoint=initial,
                    expected_revision=initial.revision,
                    next_cursor="stale-cursor",
                )
            )

        assert SQLiteDocumentRepository(self.database).get("raw-1") is None
        assert _table_count(self.database, "deduplication_identities") == 0
        assert _table_count(self.database, "work_items") == 0
        assert checkpoints.get("source-1").cursor == "cursor-1"  # type: ignore[union-attr]

    def test_connector_name_mismatch_rolls_back(
        self,
        port: SQLiteAtomicCollectionPersistence,
    ) -> None:
        initial = SQLiteCheckpointRepository(self.database).compare_and_set(
            IngestionCheckpoint(
                source_id="source-1",
                cursor="cursor-0",
                connector_version="1.0.0",
            ),
            expected_revision=None,
            connector_name="other",
        )

        with pytest.raises(CheckpointConflictError):
            port.commit_collection(
                _command(
                    current_checkpoint=initial,
                    expected_revision=initial.revision,
                )
            )

        assert SQLiteDocumentRepository(self.database).get("raw-1") is None
        assert _table_count(self.database, "work_items") == 0

    def test_connector_version_mismatch_rolls_back(
        self,
        port: SQLiteAtomicCollectionPersistence,
    ) -> None:
        SQLiteCheckpointRepository(self.database).compare_and_set(
            IngestionCheckpoint(
                source_id="source-1",
                cursor="cursor-v2",
                connector_version="2.0.0",
            ),
            expected_revision=None,
            connector_name="fixture",
        )
        stale_binding = IngestionCheckpoint(
            source_id="source-1",
            cursor="cursor-v1",
            connector_version="1.0.0",
        )

        with pytest.raises(CheckpointConflictError):
            port.commit_collection(
                _command(
                    current_checkpoint=stale_binding,
                    expected_revision=stale_binding.revision,
                )
            )

        assert SQLiteDocumentRepository(self.database).get("raw-1") is None
        assert _table_count(self.database, "deduplication_identities") == 0
        assert _table_count(self.database, "work_items") == 0

    def test_failure_after_document_insert_rolls_back(
        self,
        port: SQLiteAtomicCollectionPersistence,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def fail_identity(*args: object, **kwargs: object) -> object:
            raise IdentityConflictError("injected identity failure")

        monkeypatch.setattr(
            atomic_module,
            "_insert_or_resolve_identity",
            fail_identity,
        )

        with pytest.raises(IdentityConflictError):
            port.commit_collection(_command())

        assert _table_count(self.database, "documents") == 0
        assert _table_count(self.database, "collection_checkpoints") == 0

    def test_failure_after_identity_insert_rolls_back(
        self,
        port: SQLiteAtomicCollectionPersistence,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def fail_work(*args: object, **kwargs: object) -> object:
            raise WorkItemConflictError("injected work failure")

        monkeypatch.setattr(
            atomic_module,
            "_insert_or_resolve_work_item",
            fail_work,
        )

        with pytest.raises(WorkItemConflictError):
            port.commit_collection(_command())

        assert _table_count(self.database, "documents") == 0
        assert _table_count(self.database, "deduplication_identities") == 0

    def test_failure_after_partial_work_insert_rolls_back(
        self,
        port: SQLiteAtomicCollectionPersistence,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        documents = (_document(1), _document(2))
        original_insert = atomic_module._insert_or_resolve_work_item
        calls = 0

        def insert_then_fail(*args: object, **kwargs: object) -> object:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise WorkItemConflictError("injected second work failure")
            return original_insert(*args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(
            atomic_module,
            "_insert_or_resolve_work_item",
            insert_then_fail,
        )

        with pytest.raises(WorkItemConflictError):
            port.commit_collection(_command(documents=documents))

        assert calls == 2
        assert _table_count(self.database, "documents") == 0
        assert _table_count(self.database, "deduplication_identities") == 0
        assert _table_count(self.database, "work_items") == 0

    def test_sqlite_errors_do_not_cross_the_port(
        self,
        tmp_path: Path,
    ) -> None:
        database = SQLiteDatabase(tmp_path / "uninitialized.sqlite3")
        port = SQLiteAtomicCollectionPersistence(database)

        with pytest.raises(PersistenceOperationalError) as error:
            port.commit_collection(_command())

        assert type(error.value) is PersistenceOperationalError

    def test_public_repository_methods_are_not_composed(
        self,
        port: SQLiteAtomicCollectionPersistence,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def forbidden(*args: object, **kwargs: object) -> object:
            raise AssertionError("public repository method was called")

        monkeypatch.setattr(SQLiteDocumentRepository, "insert", forbidden)
        monkeypatch.setattr(
            SQLiteDeduplicationRepository,
            "insert_identity",
            forbidden,
        )
        monkeypatch.setattr(SQLiteWorkItemRepository, "insert", forbidden)
        monkeypatch.setattr(
            SQLiteCheckpointRepository,
            "compare_and_set",
            forbidden,
        )

        result = port.commit_collection(_command())

        assert result.documents_inserted == 1
        assert result.document_work_created == 1

    def test_file_database_restart_preserves_atomic_commit(
        self,
        port: SQLiteAtomicCollectionPersistence,
    ) -> None:
        result = port.commit_collection(_command())

        restarted = SQLiteTestDatabaseFactory.reopen(self.database)

        assert SQLiteDocumentRepository(restarted).get("raw-1") == _document()
        assert SQLiteWorkItemRepository(restarted).get(
            "work-raw-1"
        ) == _document_work(_document())
        assert (
            SQLiteCheckpointRepository(restarted).get("source-1")
            == result.checkpoint
        )


class _CountingDatabase:
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database
        self.transactions = 0

    @contextmanager
    def transaction(self) -> Iterator[object]:
        self.transactions += 1
        with self.database.transaction() as connection:
            yield connection


def test_atomic_adapter_owns_exactly_one_outer_transaction(
    sqlite_database: SQLiteDatabase,
) -> None:
    counting = _CountingDatabase(sqlite_database)
    port = SQLiteAtomicCollectionPersistence(counting)  # type: ignore[arg-type]

    port.commit_collection(_command())

    assert counting.transactions == 1
