from __future__ import annotations

import sqlite3

import pytest

from src.persistence.ingestion.errors import (
    MigrationCompatibilityError,
    PersistenceOperationalError,
)
from src.persistence.sqlite import MIGRATIONS, Migration, SQLiteDatabase, migrate
from src.persistence.sqlite.migration import MIGRATION_TOOL_VERSION
from tests.unit.persistence.sqlite.factories import SQLiteTestDatabaseFactory


def _table_names(database: SQLiteDatabase) -> set[str]:
    with database.connection() as connection:
        return {
            str(row[0])
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                """
            )
        }


def test_empty_database_initialization(
    sqlite_database_factory: SQLiteTestDatabaseFactory,
) -> None:
    database = sqlite_database_factory.create(initialize=False)

    assert not database.path.exists()
    assert migrate(database) == 1
    assert _table_names(database) == {
        "collection_checkpoints",
        "deduplication_identities",
        "documents",
        "schema_migrations",
        "work_items",
    }


def test_migration_records_explicit_registry(
    sqlite_database: SQLiteDatabase,
) -> None:
    with sqlite_database.connection() as connection:
        row = connection.execute(
            """
            SELECT version, name, checksum, tool_version
            FROM schema_migrations
            """
        ).fetchone()

    assert row is not None
    assert row["version"] == MIGRATIONS[0].version
    assert row["name"] == MIGRATIONS[0].name
    assert row["checksum"] == MIGRATIONS[0].checksum
    assert row["tool_version"] == MIGRATION_TOOL_VERSION


def test_migration_is_idempotent(sqlite_database: SQLiteDatabase) -> None:
    with sqlite_database.connection() as connection:
        applied_at = connection.execute(
            "SELECT applied_at FROM schema_migrations WHERE version = 1"
        ).fetchone()[0]

    assert migrate(sqlite_database) == 1

    with sqlite_database.connection() as connection:
        reapplied_at = connection.execute(
            "SELECT applied_at FROM schema_migrations WHERE version = 1"
        ).fetchone()[0]
        count = connection.execute(
            "SELECT COUNT(*) FROM schema_migrations"
        ).fetchone()[0]

    assert reapplied_at == applied_at
    assert count == 1


def test_checksum_mismatch_is_rejected(
    sqlite_database: SQLiteDatabase,
) -> None:
    with sqlite_database.transaction() as connection:
        connection.execute(
            "UPDATE schema_migrations SET checksum = ? WHERE version = 1",
            ("tampered",),
        )

    with pytest.raises(MigrationCompatibilityError, match="incompatible"):
        migrate(sqlite_database)


def test_newer_schema_is_rejected(sqlite_database: SQLiteDatabase) -> None:
    with sqlite_database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO schema_migrations (
                version,
                name,
                checksum,
                applied_at,
                tool_version
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (2, "future", "future-checksum", "2026-07-25T00:00:00+00:00", "future"),
        )

    with pytest.raises(MigrationCompatibilityError, match="newer"):
        migrate(sqlite_database)


def test_failed_migration_rolls_back_every_statement(
    sqlite_database: SQLiteDatabase,
) -> None:
    failing = Migration(
        version=2,
        name="failing_probe",
        statements=(
            "CREATE TABLE migration_rollback_probe (id TEXT PRIMARY KEY)",
            "INSERT INTO missing_table (id) VALUES ('failure')",
        ),
    )

    with pytest.raises(PersistenceOperationalError, match="version 2 failed"):
        migrate(sqlite_database, migrations=(*MIGRATIONS, failing))

    assert "migration_rollback_probe" not in _table_names(sqlite_database)
    with sqlite_database.connection() as connection:
        versions = tuple(
            row[0]
            for row in connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        )
    assert versions == (1,)


def test_nonempty_database_without_ledger_is_rejected(
    sqlite_database_factory: SQLiteTestDatabaseFactory,
) -> None:
    database = sqlite_database_factory.create(initialize=False)
    raw_connection = sqlite3.connect(database.path)
    try:
        raw_connection.execute("CREATE TABLE unmanaged (id TEXT PRIMARY KEY)")
        raw_connection.commit()
    finally:
        raw_connection.close()

    with pytest.raises(MigrationCompatibilityError, match="no migration ledger"):
        migrate(database)
