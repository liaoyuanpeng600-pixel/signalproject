from __future__ import annotations

import json
from dataclasses import replace

import pytest

from src.ingestion.models import IngestionCheckpoint
from src.ingestion.work import (
    CollectionWorkItem,
    DocumentProcessingWorkItem,
    ResearchWorkItem,
)
from src.persistence.ingestion import (
    PayloadCompatibilityError,
    WorkInsertDisposition,
    WorkItemConflictError,
    WorkItemRepository,
)
from src.persistence.sqlite import SQLiteWorkItemRepository
from tests.contract.persistence.test_work_item_repository_contract import (
    WorkItemRepositoryContract,
)
from tests.unit.persistence.sqlite.contracts import SQLiteContractTestMixin
from tests.unit.persistence.sqlite.factories import SQLiteTestDatabaseFactory

_CREATED_AT = "2026-07-25T00:00:00+00:00"


def _document_work(
    *,
    work_id: str = "work-document-1",
    document_id: str = "raw-1",
    idempotency_key: str = "document:raw-1",
    created_at: str = _CREATED_AT,
    schema_version: str = "1.0.0",
) -> DocumentProcessingWorkItem:
    return DocumentProcessingWorkItem(
        id=work_id,
        raw_document_id=document_id,
        idempotency_key=idempotency_key,
        created_at=created_at,
        schema_version=schema_version,
    )


def _collection_work(
    *,
    work_id: str = "work-collection-1",
    checkpoint: IngestionCheckpoint | None = None,
) -> CollectionWorkItem:
    return CollectionWorkItem(
        id=work_id,
        source_id="source-1",
        connector_name="fixture",
        connector_version="1.0.0",
        idempotency_key="collection:source-1",
        checkpoint=checkpoint,
        limit=250,
        created_at=_CREATED_AT,
    )


def _research_work(
    *,
    work_id: str = "work-research-1",
    signal_ids: tuple[str, ...] = ("signal-2", "signal-1"),
) -> ResearchWorkItem:
    return ResearchWorkItem(
        id=work_id,
        entity_id="entity-1",
        signal_ids=signal_ids,
        topic_key="earnings",
        idempotency_key="research:entity-1:earnings",
        created_at=_CREATED_AT,
    )


class TestSQLiteWorkItemRepositoryContract(
    SQLiteContractTestMixin,
    WorkItemRepositoryContract,
):
    def create_repository(self) -> WorkItemRepository:
        return SQLiteWorkItemRepository(self.database)


class TestSQLiteWorkItemRepository(SQLiteContractTestMixin):
    @pytest.fixture
    def repository(self) -> SQLiteWorkItemRepository:
        return SQLiteWorkItemRepository(self.database)

    @pytest.mark.parametrize(
        "work_item",
        [
            _collection_work(),
            _document_work(),
            _research_work(signal_ids=("signal-1", "signal-2")),
        ],
    )
    def test_supported_work_item_round_trip(
        self,
        repository: SQLiteWorkItemRepository,
        work_item: CollectionWorkItem
        | DocumentProcessingWorkItem
        | ResearchWorkItem,
    ) -> None:
        result = repository.insert(work_item)

        assert result.disposition is WorkInsertDisposition.INSERTED
        assert result.work_item == work_item
        assert repository.get(work_item.id) == work_item

    def test_missing_get_returns_none(
        self,
        repository: SQLiteWorkItemRepository,
    ) -> None:
        assert repository.get("missing-work") is None

    def test_equivalent_replay_preserves_stored_application_id(
        self,
        repository: SQLiteWorkItemRepository,
    ) -> None:
        original = _document_work()
        repository.insert(original)
        replay = replace(
            original,
            id="work-proposed",
            created_at="2026-07-25T00:05:00+00:00",
        )

        result = repository.insert(replay)

        assert result.disposition is WorkInsertDisposition.EXISTING
        assert result.work_item == original
        assert result.work_item.id == original.id
        assert repository.get(replay.id) is None

    def test_same_id_cannot_be_rebound_to_another_work_identity(
        self,
        repository: SQLiteWorkItemRepository,
    ) -> None:
        original = _document_work()
        repository.insert(original)

        with pytest.raises(WorkItemConflictError):
            repository.insert(
                _research_work(work_id=original.id)
            )

        assert repository.get(original.id) == original

    def test_same_idempotency_identity_with_different_payload_conflicts(
        self,
        repository: SQLiteWorkItemRepository,
    ) -> None:
        original = _document_work()
        repository.insert(original)

        with pytest.raises(WorkItemConflictError):
            repository.insert(
                replace(
                    original,
                    id="work-document-2",
                    raw_document_id="raw-2",
                )
            )

        assert repository.get(original.id) == original
        assert repository.get("work-document-2") is None

    def test_same_key_in_different_kinds_is_a_distinct_identity(
        self,
        repository: SQLiteWorkItemRepository,
    ) -> None:
        shared_key = "shared-key"
        document = _document_work(idempotency_key=shared_key)
        research = replace(
            _research_work(),
            idempotency_key=shared_key,
        )

        document_result = repository.insert(document)
        research_result = repository.insert(research)

        assert document_result.disposition is WorkInsertDisposition.INSERTED
        assert research_result.disposition is WorkInsertDisposition.INSERTED

    def test_collection_checkpoint_complete_round_trip(
        self,
        repository: SQLiteWorkItemRepository,
    ) -> None:
        checkpoint = IngestionCheckpoint(
            source_id="source-1",
            cursor="",
            watermark=None,
            last_success_at="2026-07-25T00:01:00+00:00",
            connector_version="1.0.0",
            revision=7,
            schema_version="checkpoint-v2",
        )
        work_item = _collection_work(checkpoint=checkpoint)

        result = repository.insert(work_item)

        assert result.work_item == work_item
        assert repository.get(work_item.id) == work_item

    def test_collection_none_checkpoint_round_trip(
        self,
        repository: SQLiteWorkItemRepository,
    ) -> None:
        work_item = _collection_work(checkpoint=None)

        result = repository.insert(work_item)

        assert result.work_item == work_item
        assert isinstance(result.work_item, CollectionWorkItem)
        assert result.work_item.checkpoint is None

    @pytest.mark.parametrize("cursor", [None, ""])
    def test_nullable_checkpoint_values_are_not_normalized(
        self,
        repository: SQLiteWorkItemRepository,
        cursor: str | None,
    ) -> None:
        checkpoint = IngestionCheckpoint(
            source_id="source-1",
            cursor=cursor,
            watermark=None,
            connector_version="1.0.0",
        )
        work_item = _collection_work(checkpoint=checkpoint)

        stored = repository.insert(work_item).work_item

        assert isinstance(stored, CollectionWorkItem)
        assert stored.checkpoint is not None
        assert stored.checkpoint.cursor == cursor
        assert stored.checkpoint.watermark is None

    def test_research_signal_ids_are_canonicalized_in_sorted_order(
        self,
        repository: SQLiteWorkItemRepository,
    ) -> None:
        work_item = _research_work(
            signal_ids=("signal-3", "signal-1", "signal-2")
        )

        stored = repository.insert(work_item).work_item

        assert isinstance(stored, ResearchWorkItem)
        assert stored.signal_ids == ("signal-1", "signal-2", "signal-3")

    def test_research_replay_ignores_signal_input_order(
        self,
        repository: SQLiteWorkItemRepository,
    ) -> None:
        original = _research_work(signal_ids=("signal-2", "signal-1"))
        first = repository.insert(original)
        replay = repository.insert(
            replace(
                original,
                id="work-research-proposed",
                signal_ids=("signal-1", "signal-2"),
            )
        )

        assert first.disposition is WorkInsertDisposition.INSERTED
        assert replay.disposition is WorkInsertDisposition.EXISTING
        assert replay.work_item == first.work_item
        assert replay.work_item.id == original.id

    def test_payload_json_is_deterministic_compact_and_sorted(
        self,
        repository: SQLiteWorkItemRepository,
    ) -> None:
        work_item = _research_work(
            signal_ids=("signal-2", "signal-1")
        )
        repository.insert(work_item)

        with self.database.connection() as connection:
            payload_json = connection.execute(
                "SELECT payload_json FROM work_items WHERE id = ?",
                (work_item.id,),
            ).fetchone()[0]

        assert payload_json == json.dumps(
            {
                "entity_id": "entity-1",
                "signal_ids": ["signal-1", "signal-2"],
                "topic_key": "earnings",
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    def test_document_payload_uses_approved_document_id_key(
        self,
        repository: SQLiteWorkItemRepository,
    ) -> None:
        work_item = _document_work(document_id="raw-9")
        repository.insert(work_item)

        with self.database.connection() as connection:
            payload_json = connection.execute(
                "SELECT payload_json FROM work_items WHERE id = ?",
                (work_item.id,),
            ).fetchone()[0]

        assert payload_json == '{"document_id":"raw-9"}'

    def test_pending_metadata_is_initialized_without_scheduling_logic(
        self,
        repository: SQLiteWorkItemRepository,
    ) -> None:
        work_item = _document_work()
        repository.insert(work_item)

        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT status, priority, available_at, created_at,
                       updated_at, revision, payload_schema_version
                FROM work_items
                WHERE id = ?
                """,
                (work_item.id,),
            ).fetchone()

        assert tuple(row) == (
            "pending",
            50,
            work_item.created_at,
            work_item.created_at,
            work_item.created_at,
            0,
            "1.0.0",
        )

    def test_unsupported_input_schema_version_is_rejected(
        self,
        repository: SQLiteWorkItemRepository,
    ) -> None:
        with pytest.raises(PayloadCompatibilityError):
            repository.insert(
                _document_work(schema_version="2.0.0")
            )

    def test_unsupported_stored_schema_version_is_rejected(
        self,
        repository: SQLiteWorkItemRepository,
    ) -> None:
        work_item = _document_work()
        repository.insert(work_item)
        with self.database.transaction() as connection:
            connection.execute(
                """
                UPDATE work_items
                SET payload_schema_version = '2.0.0'
                WHERE id = ?
                """,
                (work_item.id,),
            )

        with pytest.raises(PayloadCompatibilityError):
            repository.get(work_item.id)

    def test_repository_exposes_no_execution_or_transition_apis(
        self,
        repository: SQLiteWorkItemRepository,
    ) -> None:
        forbidden = {
            "acquire",
            "claim",
            "dead_letter",
            "fail",
            "release",
            "retry",
            "update",
        }

        assert forbidden.isdisjoint(dir(repository))

    def test_file_database_restart_preserves_work_item(
        self,
        repository: SQLiteWorkItemRepository,
    ) -> None:
        work_item = _collection_work(
            checkpoint=IngestionCheckpoint(
                source_id="source-1",
                cursor="durable-cursor",
                watermark=None,
                connector_version="1.0.0",
                revision=2,
            )
        )
        stored = repository.insert(work_item).work_item

        restarted = SQLiteTestDatabaseFactory.reopen(self.database)
        restarted_repository = SQLiteWorkItemRepository(restarted)

        assert restarted_repository.get(work_item.id) == stored
