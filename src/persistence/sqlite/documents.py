"""SQLite adapter for the frozen durable-ingestion document repository."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence

from src.core.ids import ID
from src.core.timestamps import now_utc
from src.ingestion.models import RawDocument
from src.persistence.ingestion.errors import (
    DocumentConflictError,
    PersistenceError,
    PersistenceOperationalError,
)
from src.persistence.ingestion.models import (
    DocumentInsertDisposition,
    DocumentInsertResult,
)
from src.persistence.sqlite.database import SQLiteDatabase

_DOCUMENT_COLUMNS = """
    id,
    source_id,
    external_id,
    canonical_uri,
    published_at,
    retrieved_at,
    media_type,
    title,
    content,
    raw_payload_ref,
    content_hash,
    connector_name,
    connector_version,
    provider_metadata_json,
    schema_version
"""


class SQLiteDocumentRepository:
    """Persist canonical RawDocuments without generating or replacing IDs."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def insert(self, document: RawDocument) -> DocumentInsertResult:
        """Insert or resolve an equivalent canonical document."""

        if not isinstance(document, RawDocument):
            raise TypeError("document must be a RawDocument")
        try:
            with self._database.transaction() as connection:
                return _insert_or_resolve_document(connection, document)
        except PersistenceError:
            raise
        except sqlite3.Error as exc:
            raise PersistenceOperationalError(
                "SQLite document insertion failed"
            ) from exc

    def get(self, document_id: ID) -> RawDocument | None:
        """Return a document by its application-owned ID."""

        try:
            with self._database.connection() as connection:
                return _get_document(connection, document_id)
        except PersistenceError:
            raise
        except sqlite3.Error as exc:
            raise PersistenceOperationalError(
                "SQLite document retrieval failed"
            ) from exc

    def find_by_collection_identity(
        self,
        *,
        source_id: ID,
        external_id: str,
    ) -> RawDocument | None:
        """Return the document bound to ``source_id + external_id``."""

        try:
            with self._database.connection() as connection:
                return _find_document_by_collection_identity(
                    connection,
                    source_id=source_id,
                    external_id=external_id,
                )
        except PersistenceError:
            raise
        except sqlite3.Error as exc:
            raise PersistenceOperationalError(
                "SQLite collection identity lookup failed"
            ) from exc


def _insert_or_resolve_document(
    connection: sqlite3.Connection,
    document: RawDocument,
) -> DocumentInsertResult:
    """Connection-scoped insert operation reusable by a future atomic adapter."""

    metadata_json = _encode_provider_metadata(document.provider_metadata)
    try:
        connection.execute(
            """
            INSERT INTO documents (
                id,
                source_id,
                external_id,
                canonical_uri,
                published_at,
                retrieved_at,
                media_type,
                title,
                content,
                raw_payload_ref,
                content_hash,
                connector_name,
                connector_version,
                provider_metadata_json,
                schema_version,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                document.id,
                document.source_id,
                document.external_id,
                document.canonical_uri,
                document.published_at,
                document.retrieved_at,
                document.media_type,
                document.title,
                document.content,
                document.raw_payload_ref,
                document.content_hash,
                document.connector_name,
                document.connector_version,
                metadata_json,
                document.schema_version,
                now_utc(),
            ),
        )
    except sqlite3.IntegrityError as exc:
        return _resolve_document_conflict(connection, document, exc)

    stored = _get_document(connection, document.id)
    if stored is None:
        raise PersistenceOperationalError(
            "Inserted SQLite document could not be reloaded"
        )
    return DocumentInsertResult(
        document=stored,
        disposition=DocumentInsertDisposition.INSERTED,
    )


def _resolve_document_conflict(
    connection: sqlite3.Connection,
    document: RawDocument,
    cause: sqlite3.IntegrityError,
) -> DocumentInsertResult:
    by_id = _get_document(connection, document.id)
    by_identity = _find_document_by_collection_identity(
        connection,
        source_id=document.source_id,
        external_id=document.external_id,
    )

    if (
        by_id is not None
        and by_identity is not None
        and by_id.id != by_identity.id
    ):
        raise DocumentConflictError(
            "Document ID and collection identity resolve to different documents"
        ) from cause

    existing = by_id or by_identity
    if existing is None:
        raise PersistenceOperationalError(
            "SQLite document insertion violated a storage constraint"
        ) from cause
    if not _documents_are_equivalent(existing, document):
        raise DocumentConflictError(
            "Document identity conflicts with a non-equivalent canonical document"
        ) from cause
    return DocumentInsertResult(
        document=existing,
        disposition=DocumentInsertDisposition.EXISTING,
    )


def _get_document(
    connection: sqlite3.Connection,
    document_id: ID,
) -> RawDocument | None:
    row = connection.execute(
        f"""
        SELECT {_DOCUMENT_COLUMNS}
        FROM documents
        WHERE id = ?
        """,
        (document_id,),
    ).fetchone()
    return _row_to_document(row) if row is not None else None


def _find_document_by_collection_identity(
    connection: sqlite3.Connection,
    *,
    source_id: ID,
    external_id: str,
) -> RawDocument | None:
    row = connection.execute(
        f"""
        SELECT {_DOCUMENT_COLUMNS}
        FROM documents
        WHERE source_id = ? AND external_id = ?
        """,
        (source_id, external_id),
    ).fetchone()
    return _row_to_document(row) if row is not None else None


def _row_to_document(row: sqlite3.Row) -> RawDocument:
    try:
        return RawDocument(
            id=ID(str(row["id"])),
            source_id=ID(str(row["source_id"])),
            external_id=str(row["external_id"]),
            canonical_uri=str(row["canonical_uri"]),
            published_at=str(row["published_at"]),
            retrieved_at=str(row["retrieved_at"]),
            media_type=str(row["media_type"]),
            title=str(row["title"]) if row["title"] is not None else None,
            content=str(row["content"]) if row["content"] is not None else None,
            raw_payload_ref=(
                str(row["raw_payload_ref"])
                if row["raw_payload_ref"] is not None
                else None
            ),
            content_hash=str(row["content_hash"]),
            connector_name=str(row["connector_name"]),
            connector_version=str(row["connector_version"]),
            provider_metadata=_decode_provider_metadata(
                str(row["provider_metadata_json"])
            ),
            schema_version=str(row["schema_version"]),
        )
    except (IndexError, TypeError, ValueError) as exc:
        raise PersistenceOperationalError(
            "Stored SQLite document is incompatible with RawDocument"
        ) from exc


def _encode_provider_metadata(
    metadata: Sequence[tuple[str, str]],
) -> str:
    canonical = _canonical_provider_metadata(metadata)
    return json.dumps(canonical, ensure_ascii=False, separators=(",", ":"))


def _decode_provider_metadata(value: str) -> tuple[tuple[str, str], ...]:
    decoded = json.loads(value)
    if not isinstance(decoded, list):
        raise ValueError("provider metadata must be a list of pairs")
    pairs: list[tuple[str, str]] = []
    for item in decoded:
        if (
            not isinstance(item, list)
            or len(item) != 2
            or not all(isinstance(part, str) for part in item)
        ):
            raise ValueError("provider metadata contains an invalid pair")
        pairs.append((item[0], item[1]))
    return _canonical_provider_metadata(pairs)


def _canonical_provider_metadata(
    metadata: Sequence[tuple[str, str]],
) -> tuple[tuple[str, str], ...]:
    pairs: list[tuple[str, str]] = []
    for item in metadata:
        if (
            not isinstance(item, tuple)
            or len(item) != 2
            or not all(isinstance(part, str) for part in item)
        ):
            raise TypeError("provider_metadata must contain string pairs")
        pairs.append(item)
    return tuple(sorted(pairs, key=lambda pair: (pair[0], pair[1])))


def _documents_are_equivalent(
    existing: RawDocument,
    proposed: RawDocument,
) -> bool:
    return _document_equivalence_fields(existing) == _document_equivalence_fields(
        proposed
    )


def _document_equivalence_fields(document: RawDocument) -> tuple[object, ...]:
    """Return every canonical field except the proposed application ID."""

    return (
        document.source_id,
        document.external_id,
        document.canonical_uri,
        document.published_at,
        document.retrieved_at,
        document.media_type,
        document.content_hash,
        document.content,
        document.title,
        document.raw_payload_ref,
        document.connector_name,
        document.connector_version,
        _canonical_provider_metadata(document.provider_metadata),
        document.schema_version,
    )
