"""Typed Phase 7.1 work-item foundations.

These are application contracts, not a queue implementation. Durable status,
leases, retries, and dead-letter handling belong to Phase 7.2.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.core.ids import ID, new_id
from src.core.timestamps import now_utc
from src.ingestion.models import IngestionCheckpoint

WORK_ITEM_SCHEMA_VERSION = "1.0.0"


def _validate_common(id: ID, idempotency_key: str, schema_version: str) -> None:
    if not id:
        raise ValueError("WorkItem.id is required")
    if not idempotency_key:
        raise ValueError("WorkItem.idempotency_key is required")
    if not schema_version:
        raise ValueError("WorkItem.schema_version is required")


@dataclass(frozen=True, slots=True)
class CollectionWorkItem:
    source_id: ID
    connector_name: str
    connector_version: str
    idempotency_key: str
    checkpoint: IngestionCheckpoint | None = None
    limit: int = 100
    id: ID = field(default_factory=new_id)
    created_at: str = field(default_factory=now_utc)
    schema_version: str = WORK_ITEM_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _validate_common(self.id, self.idempotency_key, self.schema_version)
        if not self.source_id:
            raise ValueError("CollectionWorkItem.source_id is required")
        if not self.connector_name:
            raise ValueError("CollectionWorkItem.connector_name is required")
        if not self.connector_version:
            raise ValueError("CollectionWorkItem.connector_version is required")
        if self.limit <= 0:
            raise ValueError("CollectionWorkItem.limit must be positive")
        if self.checkpoint is not None and self.checkpoint.source_id != self.source_id:
            raise ValueError("CollectionWorkItem checkpoint belongs to another Source")
        if (
            self.checkpoint is not None
            and self.checkpoint.connector_version != self.connector_version
        ):
            raise ValueError(
                "CollectionWorkItem checkpoint uses another Connector version"
            )


@dataclass(frozen=True, slots=True)
class DocumentProcessingWorkItem:
    raw_document_id: ID
    idempotency_key: str
    id: ID = field(default_factory=new_id)
    created_at: str = field(default_factory=now_utc)
    schema_version: str = WORK_ITEM_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _validate_common(self.id, self.idempotency_key, self.schema_version)
        if not self.raw_document_id:
            raise ValueError(
                "DocumentProcessingWorkItem.raw_document_id is required"
            )


@dataclass(frozen=True, slots=True)
class ResearchWorkItem:
    entity_id: ID
    signal_ids: tuple[ID, ...]
    topic_key: str
    idempotency_key: str
    id: ID = field(default_factory=new_id)
    created_at: str = field(default_factory=now_utc)
    schema_version: str = WORK_ITEM_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _validate_common(self.id, self.idempotency_key, self.schema_version)
        if not self.entity_id:
            raise ValueError("ResearchWorkItem.entity_id is required")
        if not self.signal_ids:
            raise ValueError("ResearchWorkItem requires at least one Signal")
        if len(self.signal_ids) != len(set(self.signal_ids)):
            raise ValueError("ResearchWorkItem.signal_ids must be unique")
        if not self.topic_key:
            raise ValueError("ResearchWorkItem.topic_key is required")
