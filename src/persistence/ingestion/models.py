"""Immutable application DTOs for durable ingestion persistence."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TypeAlias

from src.core.ids import ID
from src.ingestion.models import CollectionBatch, IngestionCheckpoint, RawDocument
from src.ingestion.work import (
    CollectionWorkItem,
    DocumentProcessingWorkItem,
    ResearchWorkItem,
)

IngestionWorkItem: TypeAlias = (
    CollectionWorkItem | DocumentProcessingWorkItem | ResearchWorkItem
)


class DocumentInsertDisposition(str, Enum):
    """Outcome of inserting or resolving a canonical RawDocument."""

    INSERTED = "inserted"
    EXISTING = "existing"


class IdentityKind(str, Enum):
    """Durable identity semantics supported by the Phase 7 foundation."""

    COLLECTION = "collection"
    CONTENT = "content"


class IdentityInsertDisposition(str, Enum):
    """Outcome of recording a durable deduplication identity claim."""

    INSERTED = "inserted"
    EXISTING = "existing"


class WorkInsertDisposition(str, Enum):
    """Outcome of inserting or resolving pending typed work."""

    INSERTED = "inserted"
    EXISTING = "existing"


@dataclass(frozen=True, slots=True)
class DocumentInsertResult:
    """A canonical document plus its idempotent insertion disposition.

    ``EXISTING`` means the adapter has already verified equivalent replay.
    Persistence stores the application-owned ``RawDocument.id`` unchanged.
    """

    document: RawDocument
    disposition: DocumentInsertDisposition

    def __post_init__(self) -> None:
        if not isinstance(self.document, RawDocument):
            raise TypeError("document must be a RawDocument")
        if not isinstance(self.disposition, DocumentInsertDisposition):
            raise TypeError("disposition must be a DocumentInsertDisposition")


@dataclass(frozen=True, slots=True)
class DeduplicationIdentity:
    """One versioned identity claim for an application-owned document ID.

    Collection identities are unique claims derived from
    ``source_id + external_id``. Content identities may be shared by documents
    with distinct provenance.
    """

    identity_kind: IdentityKind
    identity_key: str
    identity_version: str
    document_id: ID

    def __post_init__(self) -> None:
        if not isinstance(self.identity_kind, IdentityKind):
            raise TypeError("identity_kind must be an IdentityKind")
        if not self.identity_key:
            raise ValueError("identity_key is required")
        if not self.identity_version:
            raise ValueError("identity_version is required")
        if not self.document_id:
            raise ValueError("document_id is required")


@dataclass(frozen=True, slots=True)
class IdentityInsertResult:
    """Identity insertion outcome with deterministically ordered document IDs."""

    disposition: IdentityInsertDisposition
    document_ids: tuple[ID, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.disposition, IdentityInsertDisposition):
            raise TypeError("disposition must be an IdentityInsertDisposition")
        if not self.document_ids:
            raise ValueError("document_ids must not be empty")
        if len(self.document_ids) != len(set(self.document_ids)):
            raise ValueError("document_ids must be unique")
        ordered = tuple(sorted(self.document_ids, key=str))
        object.__setattr__(self, "document_ids", ordered)


@dataclass(frozen=True, slots=True)
class WorkInsertResult:
    """Typed pending work plus its idempotent insertion disposition.

    ``EXISTING`` means ``kind + idempotency_key`` resolved to an equivalent
    canonical payload. Execution state is deliberately outside this contract.
    """

    work_item: IngestionWorkItem
    disposition: WorkInsertDisposition

    def __post_init__(self) -> None:
        if not isinstance(
            self.work_item,
            CollectionWorkItem
            | DocumentProcessingWorkItem
            | ResearchWorkItem,
        ):
            raise TypeError("work_item must be a Phase 7.1 typed WorkItem")
        if not isinstance(self.disposition, WorkInsertDisposition):
            raise TypeError("disposition must be a WorkInsertDisposition")


@dataclass(frozen=True, slots=True)
class CollectionCommitCommand:
    """Inputs to the atomic durable collection boundary.

    Connector I/O has already completed. Persistence must atomically store or
    resolve the batch documents, their identity claims, corresponding
    document-processing work, and the checkpoint CAS. It never generates or
    replaces application IDs.
    """

    collection_work: CollectionWorkItem
    batch: CollectionBatch
    expected_checkpoint_revision: int | None
    next_checkpoint: IngestionCheckpoint
    document_work_items: tuple[DocumentProcessingWorkItem, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.collection_work, CollectionWorkItem):
            raise TypeError("collection_work must be a CollectionWorkItem")
        if not isinstance(self.batch, CollectionBatch):
            raise TypeError("batch must be a CollectionBatch")
        if not isinstance(self.next_checkpoint, IngestionCheckpoint):
            raise TypeError("next_checkpoint must be an IngestionCheckpoint")
        if self.batch.is_partial:
            raise ValueError("partial CollectionBatch cannot be committed")
        expected = self.expected_checkpoint_revision
        if expected is not None and (
            not isinstance(expected, int)
            or isinstance(expected, bool)
            or expected < 0
        ):
            raise ValueError(
                "expected_checkpoint_revision must be non-negative or None"
            )
        if any(
            not isinstance(item, DocumentProcessingWorkItem)
            for item in self.document_work_items
        ):
            raise TypeError(
                "document_work_items must contain DocumentProcessingWorkItem values"
            )
        source_id = self.collection_work.source_id
        if self.next_checkpoint.source_id != source_id:
            raise ValueError("next_checkpoint belongs to another Source")
        if (
            self.next_checkpoint.connector_version
            != self.collection_work.connector_version
        ):
            raise ValueError("next_checkpoint uses another Connector version")
        current = self.collection_work.checkpoint
        if current is None:
            if expected is not None:
                raise ValueError(
                    "expected_checkpoint_revision must be None for initial creation"
                )
        elif expected != current.revision:
            raise ValueError(
                "expected_checkpoint_revision must match the collection checkpoint"
            )
        for document in self.batch.records:
            if document.source_id != source_id:
                raise ValueError("batch contains a document from another Source")
            if (
                document.connector_name != self.collection_work.connector_name
                or document.connector_version
                != self.collection_work.connector_version
            ):
                raise ValueError("batch document uses another Connector binding")
        document_ids = {document.id for document in self.batch.records}
        work_document_ids = {
            item.raw_document_id for item in self.document_work_items
        }
        if len(work_document_ids) != len(self.document_work_items):
            raise ValueError("document_work_items contain duplicate document work")
        if not work_document_ids.issubset(document_ids):
            raise ValueError(
                "document_work_items must reference documents in the batch"
            )


@dataclass(frozen=True, slots=True)
class CollectionCommitResult:
    """Summary of one committed collection transaction."""

    documents_inserted: int
    documents_existing: int
    document_work_created: int
    document_work_existing: int
    checkpoint: IngestionCheckpoint

    def __post_init__(self) -> None:
        for name in (
            "documents_inserted",
            "documents_existing",
            "document_work_created",
            "document_work_existing",
        ):
            value = getattr(self, name)
            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or value < 0
            ):
                raise ValueError(f"{name} must be a non-negative integer")
        if not isinstance(self.checkpoint, IngestionCheckpoint):
            raise TypeError("checkpoint must be an IngestionCheckpoint")
