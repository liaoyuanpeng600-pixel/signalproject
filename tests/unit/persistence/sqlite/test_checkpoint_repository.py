from __future__ import annotations

from dataclasses import replace

import pytest

from src.ingestion.models import IngestionCheckpoint
from src.persistence.ingestion import (
    CheckpointConflictError,
    CheckpointRepository,
)
from src.persistence.sqlite import (
    SQLiteCheckpointRepository,
)
from tests.contract.persistence.test_checkpoint_repository_contract import (
    CheckpointRepositoryContract,
)
from tests.unit.persistence.sqlite.contracts import SQLiteContractTestMixin
from tests.unit.persistence.sqlite.factories import SQLiteTestDatabaseFactory


def _checkpoint(
    *,
    source_id: str = "source-1",
    cursor: str | None = "fixture-v1:1",
    watermark: str | None = None,
    last_success_at: str | None = None,
    connector_version: str = "1.0.0",
    revision: int = 0,
    schema_version: str = "1.0.0",
) -> IngestionCheckpoint:
    return IngestionCheckpoint(
        source_id=source_id,
        cursor=cursor,
        watermark=watermark,
        last_success_at=last_success_at,
        connector_version=connector_version,
        revision=revision,
        schema_version=schema_version,
    )


class TestSQLiteCheckpointRepositoryContract(
    SQLiteContractTestMixin,
    CheckpointRepositoryContract,
):
    def create_repository(self) -> CheckpointRepository:
        return SQLiteCheckpointRepository(self.database)


class TestSQLiteCheckpointRepository(SQLiteContractTestMixin):
    @pytest.fixture
    def repository(self) -> SQLiteCheckpointRepository:
        return SQLiteCheckpointRepository(self.database)

    def test_missing_get_returns_none(
        self,
        repository: SQLiteCheckpointRepository,
    ) -> None:
        assert repository.get("missing-source") is None

    def test_initial_creation_assigns_revision_zero(
        self,
        repository: SQLiteCheckpointRepository,
    ) -> None:
        proposed = _checkpoint(revision=41)

        stored = repository.compare_and_set(
            proposed,
            expected_revision=None,
            connector_name="fixture",
        )

        assert stored == replace(proposed, revision=0)
        assert repository.get(proposed.source_id) == stored

    def test_concurrent_initial_creation_conflicts_without_mutation(
        self,
        repository: SQLiteCheckpointRepository,
    ) -> None:
        original = repository.compare_and_set(
            _checkpoint(),
            expected_revision=None,
            connector_name="fixture",
        )

        with pytest.raises(CheckpointConflictError):
            repository.compare_and_set(
                _checkpoint(cursor="competing-cursor"),
                expected_revision=None,
                connector_name="fixture",
            )

        assert repository.get(original.source_id) == original

    def test_matching_revision_atomically_increments_revision(
        self,
        repository: SQLiteCheckpointRepository,
    ) -> None:
        created = repository.compare_and_set(
            _checkpoint(),
            expected_revision=None,
            connector_name="fixture",
        )
        proposed = replace(created, cursor="fixture-v1:2", revision=99)

        updated = repository.compare_and_set(
            proposed,
            expected_revision=created.revision,
            connector_name="fixture",
        )

        assert updated == replace(proposed, revision=created.revision + 1)
        assert repository.get(created.source_id) == updated

    def test_stale_revision_conflicts_without_mutation(
        self,
        repository: SQLiteCheckpointRepository,
    ) -> None:
        created = repository.compare_and_set(
            _checkpoint(),
            expected_revision=None,
            connector_name="fixture",
        )
        updated = repository.compare_and_set(
            replace(created, cursor="fixture-v1:2"),
            expected_revision=created.revision,
            connector_name="fixture",
        )

        with pytest.raises(CheckpointConflictError):
            repository.compare_and_set(
                replace(updated, cursor="stale-write"),
                expected_revision=created.revision,
                connector_name="fixture",
            )

        assert repository.get(created.source_id) == updated

    def test_update_of_missing_checkpoint_conflicts(
        self,
        repository: SQLiteCheckpointRepository,
    ) -> None:
        with pytest.raises(CheckpointConflictError):
            repository.compare_and_set(
                _checkpoint(),
                expected_revision=0,
                connector_name="fixture",
            )

        assert repository.get("source-1") is None

    def test_connector_name_change_conflicts(
        self,
        repository: SQLiteCheckpointRepository,
    ) -> None:
        created = repository.compare_and_set(
            _checkpoint(),
            expected_revision=None,
            connector_name="fixture",
        )

        with pytest.raises(CheckpointConflictError):
            repository.compare_and_set(
                replace(created, cursor="changed"),
                expected_revision=created.revision,
                connector_name="other",
            )

        assert repository.get(created.source_id) == created

    def test_connector_version_change_conflicts(
        self,
        repository: SQLiteCheckpointRepository,
    ) -> None:
        created = repository.compare_and_set(
            _checkpoint(),
            expected_revision=None,
            connector_name="fixture",
        )

        with pytest.raises(CheckpointConflictError):
            repository.compare_and_set(
                replace(
                    created,
                    cursor="changed",
                    connector_version="2.0.0",
                ),
                expected_revision=created.revision,
                connector_name="fixture",
            )

        assert repository.get(created.source_id) == created

    def test_full_optional_fields_round_trip(
        self,
        repository: SQLiteCheckpointRepository,
    ) -> None:
        checkpoint = _checkpoint(
            cursor=None,
            watermark="2026-07-25T00:00:00+00:00",
            last_success_at="2026-07-25T00:01:00+00:00",
            schema_version="checkpoint-v2",
        )

        stored = repository.compare_and_set(
            checkpoint,
            expected_revision=None,
            connector_name="fixture",
        )

        assert stored == checkpoint
        assert repository.get(checkpoint.source_id) == checkpoint

    def test_null_optional_fields_round_trip(
        self,
        repository: SQLiteCheckpointRepository,
    ) -> None:
        checkpoint = _checkpoint(
            cursor=None,
            watermark=None,
            last_success_at=None,
        )

        stored = repository.compare_and_set(
            checkpoint,
            expected_revision=None,
            connector_name="fixture",
        )

        assert stored == checkpoint

    def test_connector_binding_and_adapter_metadata_are_stored(
        self,
        repository: SQLiteCheckpointRepository,
    ) -> None:
        checkpoint = _checkpoint()
        repository.compare_and_set(
            checkpoint,
            expected_revision=None,
            connector_name="fixture",
        )

        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT connector_name, connector_version, updated_at
                FROM collection_checkpoints
                WHERE source_id = ?
                """,
                (checkpoint.source_id,),
            ).fetchone()

        assert row["connector_name"] == "fixture"
        assert row["connector_version"] == checkpoint.connector_version
        assert row["updated_at"]

    @pytest.mark.parametrize("expected_revision", [-1, True, 1.5])
    def test_invalid_expected_revision_is_rejected(
        self,
        repository: SQLiteCheckpointRepository,
        expected_revision: object,
    ) -> None:
        with pytest.raises(ValueError):
            repository.compare_and_set(
                _checkpoint(),
                expected_revision=expected_revision,  # type: ignore[arg-type]
                connector_name="fixture",
            )

    def test_empty_connector_name_is_rejected(
        self,
        repository: SQLiteCheckpointRepository,
    ) -> None:
        with pytest.raises(ValueError):
            repository.compare_and_set(
                _checkpoint(),
                expected_revision=None,
                connector_name="",
            )

    def test_repository_exposes_no_checkpoint_bypass_apis(
        self,
        repository: SQLiteCheckpointRepository,
    ) -> None:
        forbidden = {
            "delete",
            "force_update",
            "history",
            "set",
            "update",
        }

        assert forbidden.isdisjoint(dir(repository))

    def test_file_database_restart_preserves_checkpoint(
        self,
        repository: SQLiteCheckpointRepository,
    ) -> None:
        checkpoint = _checkpoint(
            cursor="fixture-v1:durable",
            watermark="2026-07-25T00:00:00+00:00",
        )
        stored = repository.compare_and_set(
            checkpoint,
            expected_revision=None,
            connector_name="fixture",
        )

        restarted = SQLiteTestDatabaseFactory.reopen(self.database)
        restarted_repository = SQLiteCheckpointRepository(restarted)

        assert restarted_repository.get(checkpoint.source_id) == stored
