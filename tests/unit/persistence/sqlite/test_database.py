from __future__ import annotations

from pathlib import Path

import pytest

from src.persistence.sqlite import SQLiteDatabase


def test_connection_enables_required_pragmas(
    sqlite_database: SQLiteDatabase,
) -> None:
    with sqlite_database.connection() as connection:
        foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]
        busy_timeout = connection.execute("PRAGMA busy_timeout").fetchone()[0]
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]

    assert foreign_keys == 1
    assert busy_timeout == sqlite_database.busy_timeout_ms
    assert str(journal_mode).lower() == "wal"


def test_explicit_transaction_commits_and_rolls_back(
    sqlite_database: SQLiteDatabase,
) -> None:
    with sqlite_database.transaction() as connection:
        connection.execute("CREATE TABLE transaction_probe (value TEXT NOT NULL)")
        connection.execute(
            "INSERT INTO transaction_probe (value) VALUES (?)",
            ("committed",),
        )

    with pytest.raises(RuntimeError, match="force rollback"):
        with sqlite_database.transaction() as connection:
            connection.execute(
                "INSERT INTO transaction_probe (value) VALUES (?)",
                ("rolled-back",),
            )
            raise RuntimeError("force rollback")

    with sqlite_database.connection() as connection:
        values = tuple(
            row[0]
            for row in connection.execute(
                "SELECT value FROM transaction_probe ORDER BY value"
            )
        )

    assert values == ("committed",)


def test_busy_timeout_must_be_non_negative(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="non-negative"):
        SQLiteDatabase(tmp_path / "invalid.sqlite3", busy_timeout_ms=-1)


def test_database_path_is_normalized(tmp_path: Path) -> None:
    database = SQLiteDatabase(str(tmp_path / "normalized.sqlite3"))  # type: ignore[arg-type]

    assert isinstance(database.path, Path)
