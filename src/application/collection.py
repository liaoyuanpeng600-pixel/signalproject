"""Application coordination for one bounded collection operation."""

from __future__ import annotations

from dataclasses import dataclass

from src.core.sources import Source
from src.ingestion.connector import Connector
from src.ingestion.models import CHECKPOINT_SCHEMA_VERSION, IngestionCheckpoint
from src.ingestion.service import CollectionRunner
from src.persistence.ingestion.models import (
    CollectionCommitCommand,
    CollectionCommitResult,
)
from src.persistence.ingestion.ports import (
    CheckpointRepository,
    CollectionPersistencePort,
)


@dataclass(frozen=True, slots=True)
class CollectionCoordinator:
    """Run connector work outside persistence and commit one complete batch."""

    runner: CollectionRunner
    checkpoints: CheckpointRepository
    persistence: CollectionPersistencePort

    def collect(
        self,
        *,
        connector: Connector,
        source: Source,
        limit: int = 100,
    ) -> CollectionCommitResult:
        """Collect and atomically persist one complete connector batch."""

        checkpoint = self.checkpoints.get(source.id)
        collection_work = self.runner.prepare_collection_work(
            connector=connector,
            source=source,
            checkpoint=checkpoint,
            limit=limit,
        )
        run = self.runner.collect(
            connector=connector,
            source=source,
            work_item=collection_work,
        )
        if run.batch.is_partial:
            raise ValueError("partial CollectionBatch cannot be committed")

        command = CollectionCommitCommand(
            collection_work=run.collection_work_item,
            batch=run.batch,
            expected_checkpoint_revision=(
                checkpoint.revision if checkpoint is not None else None
            ),
            next_checkpoint=self._next_checkpoint(
                connector=connector,
                source=source,
                current=checkpoint,
                next_cursor=run.batch.next_cursor,
                collected_at=run.batch.collected_at,
            ),
            document_work_items=run.document_work_items,
        )
        return self.persistence.commit_collection(command)

    @staticmethod
    def _next_checkpoint(
        *,
        connector: Connector,
        source: Source,
        current: IngestionCheckpoint | None,
        next_cursor: str | None,
        collected_at: str,
    ) -> IngestionCheckpoint:
        """Map a complete batch without interpreting cursor or watermark values."""

        return IngestionCheckpoint(
            source_id=source.id,
            cursor=(
                next_cursor
                if next_cursor is not None
                else (current.cursor if current is not None else None)
            ),
            watermark=current.watermark if current is not None else None,
            last_success_at=collected_at,
            connector_version=connector.version,
            revision=current.revision if current is not None else 0,
            schema_version=(
                current.schema_version
                if current is not None
                else CHECKPOINT_SCHEMA_VERSION
            ),
        )
