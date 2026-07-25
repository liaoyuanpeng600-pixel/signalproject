from __future__ import annotations

import sqlite3

import pytest

from src.persistence.sqlite import SQLiteDatabase


def _insert_document(
    connection: sqlite3.Connection,
    *,
    document_id: str,
    external_id: str,
) -> None:
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
            content,
            content_hash,
            connector_name,
            connector_version,
            schema_version,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            document_id,
            "source-1",
            external_id,
            f"https://example.test/{external_id}",
            "2026-07-25T00:00:00+00:00",
            "2026-07-25T00:01:00+00:00",
            "text/plain",
            "bounded content",
            f"sha256:{'a' * 64}",
            "fixture",
            "1.0.0",
            "1.0.0",
            "2026-07-25T00:01:00+00:00",
        ),
    )


def test_document_id_is_application_owned_and_collection_identity_is_unique(
    sqlite_database: SQLiteDatabase,
) -> None:
    with sqlite_database.transaction() as connection:
        _insert_document(connection, document_id="application-raw-1", external_id="item-1")
        with pytest.raises(sqlite3.IntegrityError):
            _insert_document(
                connection,
                document_id="application-raw-2",
                external_id="item-1",
            )

    with sqlite_database.connection() as connection:
        stored_id = connection.execute(
            """
            SELECT id
            FROM documents
            WHERE source_id = ? AND external_id = ?
            """,
            ("source-1", "item-1"),
        ).fetchone()[0]

    assert stored_id == "application-raw-1"


def test_collection_identity_claim_has_unique_binding(
    sqlite_database: SQLiteDatabase,
) -> None:
    with sqlite_database.transaction() as connection:
        _insert_document(connection, document_id="raw-1", external_id="item-1")
        _insert_document(connection, document_id="raw-2", external_id="item-2")
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
            ("collection", "collection-key", "raw-1", "collection-v1", "now"),
        )
        with pytest.raises(sqlite3.IntegrityError):
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
                ("collection", "collection-key", "raw-2", "collection-v1", "now"),
            )


def test_content_identity_supports_multiple_documents(
    sqlite_database: SQLiteDatabase,
) -> None:
    with sqlite_database.transaction() as connection:
        _insert_document(connection, document_id="raw-1", external_id="item-1")
        _insert_document(connection, document_id="raw-2", external_id="item-2")
        for document_id in ("raw-1", "raw-2"):
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
                ("content", "content-key", document_id, "text-v1", "now"),
            )

    with sqlite_database.connection() as connection:
        document_ids = tuple(
            row[0]
            for row in connection.execute(
                """
                SELECT document_id
                FROM deduplication_identities
                WHERE identity_kind = 'content' AND identity_key = 'content-key'
                ORDER BY document_id
                """
            )
        )

    assert document_ids == ("raw-1", "raw-2")


def test_identity_foreign_key_is_enforced(
    sqlite_database: SQLiteDatabase,
) -> None:
    with sqlite_database.transaction() as connection:
        with pytest.raises(sqlite3.IntegrityError):
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
                ("content", "content-key", "missing", "text-v1", "now"),
            )


def test_checkpoint_revision_must_be_non_negative(
    sqlite_database: SQLiteDatabase,
) -> None:
    with sqlite_database.transaction() as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO collection_checkpoints (
                    source_id,
                    connector_name,
                    connector_version,
                    revision,
                    schema_version,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("source-1", "fixture", "1.0.0", -1, "1.0.0", "now"),
            )


@pytest.mark.parametrize(
    ("status", "revision"),
    (("running", 0), ("pending", 1)),
)
def test_work_items_are_pending_at_initial_revision_only(
    sqlite_database: SQLiteDatabase,
    status: str,
    revision: int,
) -> None:
    with sqlite_database.transaction() as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO work_items (
                    id,
                    kind,
                    payload_json,
                    payload_schema_version,
                    idempotency_key,
                    status,
                    priority,
                    available_at,
                    created_at,
                    updated_at,
                    revision
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "work-1",
                    "document_processing",
                    '{"raw_document_id":"raw-1"}',
                    "1.0.0",
                    "document:raw-1",
                    status,
                    50,
                    "now",
                    "now",
                    "now",
                    revision,
                ),
            )
