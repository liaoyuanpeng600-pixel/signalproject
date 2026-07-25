"""Reusable temporary-file SQLite database factories for adapter contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import count
from pathlib import Path

from src.persistence.sqlite import SQLiteDatabase, migrate


@dataclass(slots=True)
class SQLiteTestDatabaseFactory:
    """Create isolated initialized file databases beneath one pytest temp path."""

    root: Path
    _sequence: count = field(default_factory=lambda: count(1), init=False)

    def create(
        self,
        *,
        name: str | None = None,
        initialize: bool = True,
        busy_timeout_ms: int = 5_000,
    ) -> SQLiteDatabase:
        filename = name or f"sqlite-test-{next(self._sequence)}.sqlite3"
        path = self.root / filename
        database = SQLiteDatabase(path=path, busy_timeout_ms=busy_timeout_ms)
        if initialize:
            migrate(database)
        return database

    @staticmethod
    def reopen(database: SQLiteDatabase) -> SQLiteDatabase:
        """Return a fresh connection factory for the same durable file."""

        return SQLiteDatabase(
            path=database.path,
            busy_timeout_ms=database.busy_timeout_ms,
            enable_wal=database.enable_wal,
        )
