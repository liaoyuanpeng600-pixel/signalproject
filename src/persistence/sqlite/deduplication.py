"""SQLite adapter for durable collection and content identity claims."""

from __future__ import annotations

import sqlite3

from src.core.ids import ID
from src.core.timestamps import now_utc
from src.persistence.ingestion.errors import (
    IdentityConflictError,
    PersistenceError,
    PersistenceOperationalError,
)
from src.persistence.ingestion.models import (
    DeduplicationIdentity,
    IdentityInsertDisposition,
    IdentityInsertResult,
    IdentityKind,
)
from src.persistence.sqlite.database import SQLiteDatabase


class SQLiteDeduplicationRepository:
    """Persist versioned identity claims without merging identity kinds."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def insert_identity(
        self,
        identity: DeduplicationIdentity,
    ) -> IdentityInsertResult:
        """Insert or resolve one collection or content identity claim."""

        if not isinstance(identity, DeduplicationIdentity):
            raise TypeError("identity must be a DeduplicationIdentity")
        try:
            with self._database.transaction() as connection:
                return _insert_or_resolve_identity(connection, identity)
        except PersistenceError:
            raise
        except sqlite3.Error as exc:
            raise PersistenceOperationalError(
                "SQLite identity insertion failed"
            ) from exc

    def resolve(
        self,
        *,
        identity_kind: IdentityKind,
        identity_key: str,
        identity_version: str,
    ) -> tuple[ID, ...]:
        """Return deterministic document IDs for one versioned identity."""

        _validate_identity_lookup(
            identity_kind=identity_kind,
            identity_key=identity_key,
            identity_version=identity_version,
        )
        try:
            with self._database.connection() as connection:
                return _resolve_identity(
                    connection,
                    identity_kind=identity_kind,
                    identity_key=identity_key,
                    identity_version=identity_version,
                )
        except PersistenceError:
            raise
        except sqlite3.Error as exc:
            raise PersistenceOperationalError(
                "SQLite identity resolution failed"
            ) from exc


def _insert_or_resolve_identity(
    connection: sqlite3.Connection,
    identity: DeduplicationIdentity,
) -> IdentityInsertResult:
    """Connection-scoped identity operation for future atomic persistence."""

    try:
        connection.execute(
            """
            INSERT INTO deduplication_identities (
                identity_kind,
                identity_key,
                document_id,
                identity_version,
                created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                identity.identity_kind.value,
                identity.identity_key,
                identity.document_id,
                identity.identity_version,
                now_utc(),
            ),
        )
    except sqlite3.IntegrityError as exc:
        return _resolve_identity_conflict(connection, identity, exc)

    return IdentityInsertResult(
        disposition=IdentityInsertDisposition.INSERTED,
        document_ids=_resolve_identity(
            connection,
            identity_kind=identity.identity_kind,
            identity_key=identity.identity_key,
            identity_version=identity.identity_version,
        ),
    )


def _resolve_identity_conflict(
    connection: sqlite3.Connection,
    identity: DeduplicationIdentity,
    cause: sqlite3.IntegrityError,
) -> IdentityInsertResult:
    claims = _find_identity_claims(
        connection,
        identity_kind=identity.identity_kind,
        identity_key=identity.identity_key,
    )
    same_document = next(
        (claim for claim in claims if claim.document_id == identity.document_id),
        None,
    )

    if same_document is not None:
        if same_document.identity_version != identity.identity_version:
            raise IdentityConflictError(
                "Identity version conflicts with the authoritative claim"
            ) from cause
        return IdentityInsertResult(
            disposition=IdentityInsertDisposition.EXISTING,
            document_ids=_resolve_identity(
                connection,
                identity_kind=identity.identity_kind,
                identity_key=identity.identity_key,
                identity_version=identity.identity_version,
            ),
        )

    if identity.identity_kind is IdentityKind.COLLECTION and claims:
        raise IdentityConflictError(
            "Collection identity is already bound to another document"
        ) from cause

    if not _document_exists(connection, identity.document_id):
        raise IdentityConflictError(
            "Identity claim references an unknown document"
        ) from cause

    raise PersistenceOperationalError(
        "SQLite identity insertion violated an unexpected storage constraint"
    ) from cause


def _resolve_identity(
    connection: sqlite3.Connection,
    *,
    identity_kind: IdentityKind,
    identity_key: str,
    identity_version: str,
) -> tuple[ID, ...]:
    rows = connection.execute(
        """
        SELECT document_id
        FROM deduplication_identities
        WHERE identity_kind = ?
          AND identity_key = ?
          AND identity_version = ?
        ORDER BY document_id
        """,
        (identity_kind.value, identity_key, identity_version),
    ).fetchall()
    return tuple(ID(str(row["document_id"])) for row in rows)


def _find_identity_claims(
    connection: sqlite3.Connection,
    *,
    identity_kind: IdentityKind,
    identity_key: str,
) -> tuple[DeduplicationIdentity, ...]:
    rows = connection.execute(
        """
        SELECT identity_kind, identity_key, identity_version, document_id
        FROM deduplication_identities
        WHERE identity_kind = ? AND identity_key = ?
        ORDER BY document_id
        """,
        (identity_kind.value, identity_key),
    ).fetchall()
    return tuple(_row_to_identity(row) for row in rows)


def _row_to_identity(row: sqlite3.Row) -> DeduplicationIdentity:
    try:
        return DeduplicationIdentity(
            identity_kind=IdentityKind(str(row["identity_kind"])),
            identity_key=str(row["identity_key"]),
            identity_version=str(row["identity_version"]),
            document_id=ID(str(row["document_id"])),
        )
    except (IndexError, TypeError, ValueError) as exc:
        raise PersistenceOperationalError(
            "Stored SQLite identity is incompatible with DeduplicationIdentity"
        ) from exc


def _document_exists(
    connection: sqlite3.Connection,
    document_id: ID,
) -> bool:
    row = connection.execute(
        "SELECT 1 FROM documents WHERE id = ?",
        (document_id,),
    ).fetchone()
    return row is not None


def _validate_identity_lookup(
    *,
    identity_kind: IdentityKind,
    identity_key: str,
    identity_version: str,
) -> None:
    if not isinstance(identity_kind, IdentityKind):
        raise TypeError("identity_kind must be an IdentityKind")
    if not identity_key:
        raise ValueError("identity_key is required")
    if not identity_version:
        raise ValueError("identity_version is required")
