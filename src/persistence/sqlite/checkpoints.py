"""SQLite adapter for connector-bound ingestion checkpoint CAS."""

from __future__ import annotations

import sqlite3

from src.core.ids import ID
from src.core.timestamps import now_utc
from src.ingestion.models import IngestionCheckpoint
from src.persistence.ingestion.errors import (
    CheckpointConflictError,
    PersistenceError,
    PersistenceOperationalError,
)
from src.persistence.sqlite.database import SQLiteDatabase

_CHECKPOINT_COLUMNS = """
    source_id,
    cursor,
    watermark,
    last_success_at,
    connector_version,
    revision,
    schema_version
"""


class SQLiteCheckpointRepository:
    """Persist checkpoints through connector-bound compare-and-set."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def get(self, source_id: ID) -> IngestionCheckpoint | None:
        """Return the committed checkpoint for a source."""

        try:
            with self._database.connection() as connection:
                return _get_checkpoint(connection, source_id)
        except PersistenceError:
            raise
        except sqlite3.Error as exc:
            raise PersistenceOperationalError(
                "SQLite checkpoint retrieval failed"
            ) from exc

    def compare_and_set(
        self,
        checkpoint: IngestionCheckpoint,
        *,
        expected_revision: int | None,
        connector_name: str,
    ) -> IngestionCheckpoint:
        """Create or atomically advance a connector-bound checkpoint."""

        _validate_compare_and_set(
            checkpoint=checkpoint,
            expected_revision=expected_revision,
            connector_name=connector_name,
        )
        try:
            with self._database.transaction() as connection:
                return _compare_and_set_checkpoint(
                    connection,
                    checkpoint,
                    expected_revision=expected_revision,
                    connector_name=connector_name,
                )
        except PersistenceError:
            raise
        except sqlite3.Error as exc:
            raise PersistenceOperationalError(
                "SQLite checkpoint compare-and-set failed"
            ) from exc


def _compare_and_set_checkpoint(
    connection: sqlite3.Connection,
    checkpoint: IngestionCheckpoint,
    *,
    expected_revision: int | None,
    connector_name: str,
) -> IngestionCheckpoint:
    """Connection-scoped CAS for future atomic collection persistence."""

    if expected_revision is None:
        return _create_checkpoint(
            connection,
            checkpoint,
            connector_name=connector_name,
        )
    return _update_checkpoint(
        connection,
        checkpoint,
        expected_revision=expected_revision,
        connector_name=connector_name,
    )


def _create_checkpoint(
    connection: sqlite3.Connection,
    checkpoint: IngestionCheckpoint,
    *,
    connector_name: str,
) -> IngestionCheckpoint:
    try:
        connection.execute(
            """
            INSERT INTO collection_checkpoints (
                source_id,
                cursor,
                watermark,
                last_success_at,
                connector_name,
                connector_version,
                revision,
                schema_version,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (
                checkpoint.source_id,
                checkpoint.cursor,
                checkpoint.watermark,
                checkpoint.last_success_at,
                connector_name,
                checkpoint.connector_version,
                checkpoint.schema_version,
                now_utc(),
            ),
        )
    except sqlite3.IntegrityError as exc:
        raise CheckpointConflictError(
            "Checkpoint already exists or violates creation constraints"
        ) from exc

    stored = _get_checkpoint(connection, checkpoint.source_id)
    if stored is None:
        raise PersistenceOperationalError(
            "Created SQLite checkpoint could not be reloaded"
        )
    return stored


def _update_checkpoint(
    connection: sqlite3.Connection,
    checkpoint: IngestionCheckpoint,
    *,
    expected_revision: int,
    connector_name: str,
) -> IngestionCheckpoint:
    cursor = connection.execute(
        """
        UPDATE collection_checkpoints
        SET cursor = ?,
            watermark = ?,
            last_success_at = ?,
            revision = revision + 1,
            schema_version = ?,
            updated_at = ?
        WHERE source_id = ?
          AND revision = ?
          AND connector_name = ?
          AND connector_version = ?
        """,
        (
            checkpoint.cursor,
            checkpoint.watermark,
            checkpoint.last_success_at,
            checkpoint.schema_version,
            now_utc(),
            checkpoint.source_id,
            expected_revision,
            connector_name,
            checkpoint.connector_version,
        ),
    )
    if cursor.rowcount != 1:
        raise CheckpointConflictError(
            "Checkpoint is missing, stale, or bound to another connector"
        )

    stored = _get_checkpoint(connection, checkpoint.source_id)
    if stored is None:
        raise PersistenceOperationalError(
            "Updated SQLite checkpoint could not be reloaded"
        )
    return stored


def _get_checkpoint(
    connection: sqlite3.Connection,
    source_id: ID,
) -> IngestionCheckpoint | None:
    row = connection.execute(
        f"""
        SELECT {_CHECKPOINT_COLUMNS}
        FROM collection_checkpoints
        WHERE source_id = ?
        """,
        (source_id,),
    ).fetchone()
    return _row_to_checkpoint(row) if row is not None else None


def _row_to_checkpoint(row: sqlite3.Row) -> IngestionCheckpoint:
    try:
        return IngestionCheckpoint(
            source_id=ID(str(row["source_id"])),
            cursor=str(row["cursor"]) if row["cursor"] is not None else None,
            watermark=(
                str(row["watermark"]) if row["watermark"] is not None else None
            ),
            last_success_at=(
                str(row["last_success_at"])
                if row["last_success_at"] is not None
                else None
            ),
            connector_version=str(row["connector_version"]),
            revision=int(row["revision"]),
            schema_version=str(row["schema_version"]),
        )
    except (IndexError, TypeError, ValueError) as exc:
        raise PersistenceOperationalError(
            "Stored SQLite checkpoint is incompatible with IngestionCheckpoint"
        ) from exc


def _validate_compare_and_set(
    *,
    checkpoint: IngestionCheckpoint,
    expected_revision: int | None,
    connector_name: str,
) -> None:
    if not isinstance(checkpoint, IngestionCheckpoint):
        raise TypeError("checkpoint must be an IngestionCheckpoint")
    if expected_revision is not None and (
        not isinstance(expected_revision, int)
        or isinstance(expected_revision, bool)
        or expected_revision < 0
    ):
        raise ValueError("expected_revision must be non-negative or None")
    if not connector_name:
        raise ValueError("connector_name is required")
