"""Process-level construction for the Phase 7 SQLite ingestion slice."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.application.collection import CollectionCoordinator
from src.ingestion.service import CollectionRunner
from src.persistence.ingestion.ports import (
    CheckpointRepository,
    CollectionPersistencePort,
    DeduplicationRepository,
    DocumentRepository,
    WorkItemRepository,
)
from src.persistence.sqlite import (
    SQLiteAtomicCollectionPersistence,
    SQLiteCheckpointRepository,
    SQLiteDatabase,
    SQLiteDeduplicationRepository,
    SQLiteDocumentRepository,
    SQLiteWorkItemRepository,
    migrate,
)


@dataclass(frozen=True, slots=True)
class SQLiteIngestionConfig:
    """Immutable infrastructure configuration supplied by the process boundary."""

    database_path: Path
    busy_timeout_ms: int = 5_000
    enable_wal: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "database_path", Path(self.database_path))
        if self.busy_timeout_ms < 0:
            raise ValueError("busy_timeout_ms must be non-negative")


@dataclass(frozen=True, slots=True)
class IngestionComposition:
    """Constructed application graph exposing ports rather than SQLite internals."""

    coordinator: CollectionCoordinator
    documents: DocumentRepository
    deduplication: DeduplicationRepository
    checkpoints: CheckpointRepository
    work_items: WorkItemRepository
    collection_persistence: CollectionPersistencePort


def compose_sqlite_ingestion(
    config: SQLiteIngestionConfig,
) -> IngestionComposition:
    """Migrate one file-backed database and construct the ingestion object graph."""

    if not isinstance(config, SQLiteIngestionConfig):
        raise TypeError("config must be a SQLiteIngestionConfig")

    database = SQLiteDatabase(
        path=config.database_path,
        busy_timeout_ms=config.busy_timeout_ms,
        enable_wal=config.enable_wal,
    )
    migrate(database)

    documents = SQLiteDocumentRepository(database)
    deduplication = SQLiteDeduplicationRepository(database)
    checkpoints = SQLiteCheckpointRepository(database)
    work_items = SQLiteWorkItemRepository(database)
    collection_persistence = SQLiteAtomicCollectionPersistence(database)
    coordinator = CollectionCoordinator(
        runner=CollectionRunner(),
        checkpoints=checkpoints,
        persistence=collection_persistence,
    )

    return IngestionComposition(
        coordinator=coordinator,
        documents=documents,
        deduplication=deduplication,
        checkpoints=checkpoints,
        work_items=work_items,
        collection_persistence=collection_persistence,
    )
