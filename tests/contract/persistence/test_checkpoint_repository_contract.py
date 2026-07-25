from dataclasses import replace

import pytest

from src.ingestion.models import IngestionCheckpoint
from src.persistence.ingestion import (
    CheckpointConflictError,
    CheckpointRepository,
)


def _checkpoint(*, version: str = "1.0.0") -> IngestionCheckpoint:
    return IngestionCheckpoint(
        source_id="source-1",
        cursor="fixture-v1:1",
        connector_version=version,
    )


class CheckpointRepositoryContract:
    """Reusable CAS suite for future persistence adapters."""

    def create_repository(self) -> CheckpointRepository:
        raise NotImplementedError

    def test_initial_create_and_concurrent_create_conflict(self) -> None:
        repository = self.create_repository()
        created = repository.compare_and_set(
            _checkpoint(),
            expected_revision=None,
            connector_name="fixture",
        )

        assert created.revision == 0
        with pytest.raises(CheckpointConflictError):
            repository.compare_and_set(
                _checkpoint(),
                expected_revision=None,
                connector_name="fixture",
            )

    def test_matching_revision_updates_and_stale_revision_conflicts(self) -> None:
        repository = self.create_repository()
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

        assert updated.revision == created.revision + 1
        with pytest.raises(CheckpointConflictError):
            repository.compare_and_set(
                replace(updated, cursor="fixture-v1:3"),
                expected_revision=created.revision,
                connector_name="fixture",
            )

    def test_connector_binding_conflicts(self) -> None:
        repository = self.create_repository()
        created = repository.compare_and_set(
            _checkpoint(),
            expected_revision=None,
            connector_name="fixture",
        )

        with pytest.raises(CheckpointConflictError):
            repository.compare_and_set(
                replace(created, connector_version="2.0.0"),
                expected_revision=created.revision,
                connector_name="other",
            )
