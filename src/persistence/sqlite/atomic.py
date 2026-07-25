"""Atomic SQLite implementation of the collection persistence boundary."""

from __future__ import annotations

import sqlite3

from src.ingestion.deduplication import (
    IDENTITY_VERSION,
    NORMALIZATION_VERSION,
    collection_identity,
)
from src.persistence.ingestion.errors import (
    PersistenceError,
    PersistenceOperationalError,
)
from src.persistence.ingestion.models import (
    CollectionCommitCommand,
    CollectionCommitResult,
    DeduplicationIdentity,
    DocumentInsertDisposition,
    IdentityKind,
    WorkInsertDisposition,
)
from src.persistence.sqlite.checkpoints import (
    _compare_and_set_checkpoint,
    _validate_compare_and_set,
)
from src.persistence.sqlite.database import SQLiteDatabase
from src.persistence.sqlite.deduplication import _insert_or_resolve_identity
from src.persistence.sqlite.documents import _insert_or_resolve_document
from src.persistence.sqlite.work_items import (
    _insert_or_resolve_work_item,
    _validate_work_item,
)


class SQLiteAtomicCollectionPersistence:
    """Commit one complete collection command in one SQLite transaction."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def commit_collection(
        self,
        command: CollectionCommitCommand,
    ) -> CollectionCommitResult:
        """Atomically persist documents, identities, work, and checkpoint CAS."""

        if not isinstance(command, CollectionCommitCommand):
            raise TypeError("command must be a CollectionCommitCommand")
        for work_item in command.document_work_items:
            _validate_work_item(work_item)
        _validate_compare_and_set(
            checkpoint=command.next_checkpoint,
            expected_revision=command.expected_checkpoint_revision,
            connector_name=command.collection_work.connector_name,
        )

        try:
            with self._database.transaction() as connection:
                documents_inserted = 0
                documents_existing = 0
                document_work_created = 0
                document_work_existing = 0

                for proposed_document in command.batch.records:
                    document_result = _insert_or_resolve_document(
                        connection,
                        proposed_document,
                    )
                    if (
                        document_result.disposition
                        is DocumentInsertDisposition.INSERTED
                    ):
                        documents_inserted += 1
                    else:
                        documents_existing += 1

                    document = document_result.document
                    _insert_or_resolve_identity(
                        connection,
                        DeduplicationIdentity(
                            identity_kind=IdentityKind.COLLECTION,
                            identity_key=collection_identity(
                                document.source_id,
                                document.external_id,
                            ),
                            identity_version=IDENTITY_VERSION,
                            document_id=document.id,
                        ),
                    )
                    _insert_or_resolve_identity(
                        connection,
                        DeduplicationIdentity(
                            identity_kind=IdentityKind.CONTENT,
                            identity_key=document.content_hash,
                            identity_version=NORMALIZATION_VERSION,
                            document_id=document.id,
                        ),
                    )

                for work_item in command.document_work_items:
                    work_result = _insert_or_resolve_work_item(
                        connection,
                        work_item,
                    )
                    if work_result.disposition is WorkInsertDisposition.INSERTED:
                        document_work_created += 1
                    else:
                        document_work_existing += 1

                checkpoint = _compare_and_set_checkpoint(
                    connection,
                    command.next_checkpoint,
                    expected_revision=command.expected_checkpoint_revision,
                    connector_name=command.collection_work.connector_name,
                )

                return CollectionCommitResult(
                    documents_inserted=documents_inserted,
                    documents_existing=documents_existing,
                    document_work_created=document_work_created,
                    document_work_existing=document_work_existing,
                    checkpoint=checkpoint,
                )
        except PersistenceError:
            raise
        except sqlite3.Error as exc:
            raise PersistenceOperationalError(
                "SQLite atomic collection persistence failed"
            ) from exc
