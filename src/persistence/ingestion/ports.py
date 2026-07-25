"""Narrow repository ports for the Phase 7 ingestion persistence boundary."""

from __future__ import annotations

from typing import Protocol

from src.core.ids import ID
from src.ingestion.models import IngestionCheckpoint, RawDocument
from src.persistence.ingestion.models import (
    CollectionCommitCommand,
    CollectionCommitResult,
    DeduplicationIdentity,
    DocumentInsertResult,
    IdentityInsertResult,
    IdentityKind,
    IngestionWorkItem,
    WorkInsertResult,
)


class DocumentRepository(Protocol):
    """Store application-owned RawDocument IDs without independently committing."""

    def insert(self, document: RawDocument) -> DocumentInsertResult:
        """Insert or resolve equivalent replay; fail closed on disagreement."""
        ...

    def get(self, document_id: ID) -> RawDocument | None:
        """Return the canonical document for an application-owned ID."""
        ...

    def find_by_collection_identity(
        self,
        *,
        source_id: ID,
        external_id: str,
    ) -> RawDocument | None:
        """Resolve the unique ``source_id + external_id`` identity."""
        ...


class CheckpointRepository(Protocol):
    """Persist opaque cursors through connector-bound compare-and-set."""

    def get(self, source_id: ID) -> IngestionCheckpoint | None:
        """Return the committed checkpoint without interpreting its cursor."""
        ...

    def compare_and_set(
        self,
        checkpoint: IngestionCheckpoint,
        *,
        expected_revision: int | None,
        connector_name: str,
    ) -> IngestionCheckpoint:
        """Create or update a checkpoint without independently committing.

        ``expected_revision=None`` means the checkpoint must not exist.
        Initial creation, stale revision, and connector-binding conflicts raise
        ``CheckpointConflictError`` at the persistence boundary.
        """
        ...


class DeduplicationRepository(Protocol):
    """Record durable identity claims without replacing Phase 7.1 pure dedupe."""

    def insert_identity(
        self,
        identity: DeduplicationIdentity,
    ) -> IdentityInsertResult:
        """Insert or resolve a claim without independently committing."""
        ...

    def resolve(
        self,
        *,
        identity_kind: IdentityKind,
        identity_key: str,
        identity_version: str,
    ) -> tuple[ID, ...]:
        """Return deterministic IDs; content identities may resolve to many."""
        ...


class WorkItemRepository(Protocol):
    """Persist and inspect pending Phase 7.1 typed work only."""

    def insert(self, work_item: IngestionWorkItem) -> WorkInsertResult:
        """Insert or resolve equivalent pending work without committing."""
        ...

    def get(self, work_item_id: ID) -> IngestionWorkItem | None:
        """Return typed application work without an execution-state adapter."""
        ...


class CollectionPersistencePort(Protocol):
    """Application-facing atomic collection persistence boundary."""

    def commit_collection(
        self,
        command: CollectionCommitCommand,
    ) -> CollectionCommitResult:
        """Commit documents, identities, document work, and checkpoint CAS.

        All components succeed in one adapter-owned transaction or all fail.
        Connector I/O and partial batches are outside this boundary. The
        application never receives a connection or transaction object.
        """
        ...
