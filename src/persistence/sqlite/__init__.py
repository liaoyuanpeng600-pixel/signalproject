"""SQLite infrastructure and repository adapters for ingestion persistence."""

from __future__ import annotations

from src.persistence.sqlite.atomic import SQLiteAtomicCollectionPersistence
from src.persistence.sqlite.checkpoints import SQLiteCheckpointRepository
from src.persistence.sqlite.database import SQLiteDatabase
from src.persistence.sqlite.deduplication import SQLiteDeduplicationRepository
from src.persistence.sqlite.documents import SQLiteDocumentRepository
from src.persistence.sqlite.migration import MIGRATIONS, Migration, migrate
from src.persistence.sqlite.work_items import SQLiteWorkItemRepository

__all__ = [
    "MIGRATIONS",
    "Migration",
    "SQLiteAtomicCollectionPersistence",
    "SQLiteCheckpointRepository",
    "SQLiteDatabase",
    "SQLiteDeduplicationRepository",
    "SQLiteDocumentRepository",
    "SQLiteWorkItemRepository",
    "migrate",
]
