from __future__ import annotations

from src.persistence.sqlite import SQLiteDatabase, migrate
from tests.unit.persistence.sqlite.factories import SQLiteTestDatabaseFactory


def test_file_database_preserves_schema_and_rows_across_restart(
    sqlite_database_factory: SQLiteTestDatabaseFactory,
) -> None:
    database = sqlite_database_factory.create()
    with database.transaction() as connection:
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
                "application-raw-1",
                "source-1",
                "item-1",
                "https://example.test/item-1",
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

    restarted = sqlite_database_factory.reopen(database)
    assert migrate(restarted) == 1
    with restarted.connection() as connection:
        row = connection.execute(
            "SELECT id, external_id FROM documents WHERE id = ?",
            ("application-raw-1",),
        ).fetchone()

    assert row is not None
    assert tuple(row) == ("application-raw-1", "item-1")
    assert restarted.path == database.path
    assert isinstance(restarted, SQLiteDatabase)
