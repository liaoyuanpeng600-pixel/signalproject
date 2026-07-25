"""Stable public persistence contracts for Phase 7 ingestion."""

from __future__ import annotations

from src.persistence.ingestion.errors import (
    CheckpointConflictError,
    DocumentConflictError,
    IdentityConflictError,
    MigrationCompatibilityError,
    PayloadCompatibilityError,
    PersistenceError,
    PersistenceOperationalError,
    WorkItemConflictError,
)
from src.persistence.ingestion.models import (
    CollectionCommitCommand,
    CollectionCommitResult,
    DeduplicationIdentity,
    DocumentInsertDisposition,
    DocumentInsertResult,
    IdentityInsertDisposition,
    IdentityInsertResult,
    IdentityKind,
    IngestionWorkItem,
    WorkInsertDisposition,
    WorkInsertResult,
)
from src.persistence.ingestion.ports import (
    CheckpointRepository,
    CollectionPersistencePort,
    DeduplicationRepository,
    DocumentRepository,
    WorkItemRepository,
)

__all__ = [
    "CheckpointConflictError",
    "CheckpointRepository",
    "CollectionCommitCommand",
    "CollectionCommitResult",
    "CollectionPersistencePort",
    "DeduplicationIdentity",
    "DeduplicationRepository",
    "DocumentConflictError",
    "DocumentInsertDisposition",
    "DocumentInsertResult",
    "DocumentRepository",
    "IdentityConflictError",
    "IdentityInsertDisposition",
    "IdentityInsertResult",
    "IdentityKind",
    "IngestionWorkItem",
    "MigrationCompatibilityError",
    "PayloadCompatibilityError",
    "PersistenceError",
    "PersistenceOperationalError",
    "WorkInsertDisposition",
    "WorkInsertResult",
    "WorkItemConflictError",
    "WorkItemRepository",
]
