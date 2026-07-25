"""Minimal ordered and checksummed SQLite migration runner."""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone

from src.persistence.ingestion.errors import (
    MigrationCompatibilityError,
    PersistenceOperationalError,
)
from src.persistence.sqlite.database import SQLiteDatabase
from src.persistence.sqlite.migrations import v0001_ingestion

MIGRATION_TOOL_VERSION = "phase7.2-migration-v1"


@dataclass(frozen=True, slots=True)
class Migration:
    """One immutable, explicitly ordered database migration."""

    version: int
    name: str
    statements: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.version <= 0:
            raise ValueError("migration version must be positive")
        if not self.name:
            raise ValueError("migration name is required")
        if not self.statements or any(not statement.strip() for statement in self.statements):
            raise ValueError("migration statements must not be empty")

    @property
    def checksum(self) -> str:
        payload = "\n-- migration statement --\n".join(
            statement.strip() for statement in self.statements
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        version=v0001_ingestion.VERSION,
        name=v0001_ingestion.NAME,
        statements=v0001_ingestion.STATEMENTS,
    ),
)


@dataclass(frozen=True, slots=True)
class _AppliedMigration:
    version: int
    name: str
    checksum: str


def migrate(
    database: SQLiteDatabase,
    *,
    migrations: Sequence[Migration] = MIGRATIONS,
) -> int:
    """Validate and apply migrations, returning the current schema version."""

    registry = tuple(migrations)
    _validate_registry(registry)

    with database.connection() as connection:
        applied = _read_applied_migrations(connection)
        _validate_applied_migrations(applied, registry)

    for migration in registry:
        _apply_if_needed(database, migration, registry)

    with database.connection() as connection:
        applied = _read_applied_migrations(connection)
        _validate_applied_migrations(applied, registry)
    return applied[-1].version if applied else 0


def _validate_registry(migrations: tuple[Migration, ...]) -> None:
    if not migrations:
        raise ValueError("at least one migration is required")
    versions = tuple(migration.version for migration in migrations)
    names = tuple(migration.name for migration in migrations)
    if versions != tuple(range(1, len(migrations) + 1)):
        raise ValueError("migration registry must be contiguous and start at version 1")
    if len(names) != len(set(names)):
        raise ValueError("migration names must be unique")


def _read_applied_migrations(
    connection: sqlite3.Connection,
) -> tuple[_AppliedMigration, ...]:
    tables = {
        str(row[0])
        for row in connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            """
        )
    }
    if "schema_migrations" not in tables:
        if tables:
            raise MigrationCompatibilityError(
                "SQLite database has schema objects but no migration ledger"
            )
        return ()

    try:
        rows = connection.execute(
            """
            SELECT version, name, checksum
            FROM schema_migrations
            ORDER BY version
            """
        ).fetchall()
    except sqlite3.Error as exc:
        raise MigrationCompatibilityError(
            "SQLite migration ledger is not readable"
        ) from exc
    return tuple(
        _AppliedMigration(
            version=int(row["version"]),
            name=str(row["name"]),
            checksum=str(row["checksum"]),
        )
        for row in rows
    )


def _validate_applied_migrations(
    applied: tuple[_AppliedMigration, ...],
    registry: tuple[Migration, ...],
) -> None:
    if not applied:
        return

    supported_version = registry[-1].version
    if applied[-1].version > supported_version:
        raise MigrationCompatibilityError(
            "SQLite database schema is newer than this application supports"
        )

    expected_versions = tuple(range(1, applied[-1].version + 1))
    actual_versions = tuple(migration.version for migration in applied)
    if actual_versions != expected_versions:
        raise MigrationCompatibilityError(
            "SQLite migration ledger contains a version gap"
        )

    registry_by_version = {migration.version: migration for migration in registry}
    for recorded in applied:
        expected = registry_by_version.get(recorded.version)
        if expected is None:
            raise MigrationCompatibilityError(
                "SQLite migration ledger contains an unsupported version"
            )
        if recorded.name != expected.name or recorded.checksum != expected.checksum:
            raise MigrationCompatibilityError(
                f"SQLite migration version {recorded.version} is incompatible"
            )


def _apply_if_needed(
    database: SQLiteDatabase,
    migration: Migration,
    registry: tuple[Migration, ...],
) -> None:
    try:
        with database.transaction(mode="IMMEDIATE") as connection:
            applied = _read_applied_migrations(connection)
            _validate_applied_migrations(applied, registry)
            if any(recorded.version == migration.version for recorded in applied):
                return

            current_version = applied[-1].version if applied else 0
            if migration.version != current_version + 1:
                raise MigrationCompatibilityError(
                    "SQLite migrations cannot be applied out of order"
                )

            for statement in migration.statements:
                connection.execute(statement)
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
                (
                    migration.version,
                    migration.name,
                    migration.checksum,
                    datetime.now(timezone.utc).isoformat(),
                    MIGRATION_TOOL_VERSION,
                ),
            )
    except sqlite3.Error as exc:
        raise PersistenceOperationalError(
            f"SQLite migration version {migration.version} failed"
        ) from exc
