from dataclasses import replace

import pytest

from src.ingestion.work import DocumentProcessingWorkItem
from src.persistence.ingestion import (
    WorkInsertDisposition,
    WorkItemConflictError,
    WorkItemRepository,
)


def _work() -> DocumentProcessingWorkItem:
    return DocumentProcessingWorkItem(
        id="work-1",
        raw_document_id="raw-1",
        idempotency_key="document:raw-1",
    )


class WorkItemRepositoryContract:
    """Reusable pending typed-work suite for future persistence adapters."""

    def create_repository(self) -> WorkItemRepository:
        raise NotImplementedError

    def test_insert_and_equivalent_replay(self) -> None:
        repository = self.create_repository()
        work = _work()

        first = repository.insert(work)
        replay = repository.insert(work)

        assert first.disposition is WorkInsertDisposition.INSERTED
        assert replay.disposition is WorkInsertDisposition.EXISTING
        assert replay.work_item == work

    def test_same_idempotency_key_with_different_payload_conflicts(self) -> None:
        repository = self.create_repository()
        work = _work()
        repository.insert(work)

        with pytest.raises(WorkItemConflictError):
            repository.insert(replace(work, id="work-2", raw_document_id="raw-2"))
