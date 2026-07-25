"""SQLite connection and transaction management for infrastructure adapters."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from src.persistence.ingestion.errors import PersistenceOperationalError

TransactionMode = Literal["DEFERRED", "IMMEDIATE", "EXCLUSIVE"]


@dataclass(frozen=True, slots=True)
class SQLiteDatabase:
    """Path-bound SQLite connection factory with explicit transaction control.

    Connections are short-lived and remain inside the SQLite infrastructure
    adapter. Persistence ports never accept or return ``sqlite3.Connection``.
    """

    path: Path
    busy_timeout_ms: int = 5_000
    enable_wal: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", Path(self.path))
        if self.busy_timeout_ms < 0:
            raise ValueError("busy_timeout_ms must be non-negative")

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Yield a configured infrastructure connection and always close it."""

        connection = self._open()
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(
        self,
        *,
        mode: TransactionMode = "IMMEDIATE",
    ) -> Iterator[sqlite3.Connection]:
        """Yield one explicitly controlled transaction.

        ``IMMEDIATE`` is the default for short ingestion writes so competing
        writers are serialized before performing any application mutation.
        """

        if mode not in {"DEFERRED", "IMMEDIATE", "EXCLUSIVE"}:
            raise ValueError(f"unsupported SQLite transaction mode: {mode}")

        with self.connection() as connection:
            try:
                connection.execute(f"BEGIN {mode}")
            except sqlite3.Error as exc:
                raise PersistenceOperationalError(
                    "Unable to begin SQLite transaction"
                ) from exc

            try:
                yield connection
            except BaseException:
                if connection.in_transaction:
                    try:
                        connection.rollback()
                    except sqlite3.Error as exc:
                        raise PersistenceOperationalError(
                            "Unable to roll back SQLite transaction"
                        ) from exc
                raise
            else:
                try:
                    connection.commit()
                except sqlite3.Error as exc:
                    if connection.in_transaction:
                        connection.rollback()
                    raise PersistenceOperationalError(
                        "Unable to commit SQLite transaction"
                    ) from exc

    def _open(self) -> sqlite3.Connection:
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(
                self.path,
                timeout=self.busy_timeout_ms / 1_000,
                isolation_level=None,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute(f"PRAGMA busy_timeout = {self.busy_timeout_ms}")
            if self.enable_wal:
                # SQLite returns the active mode. Unsupported filesystems keep
                # their existing mode without changing correctness semantics.
                connection.execute("PRAGMA journal_mode = WAL").fetchone()
            foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()
            if foreign_keys is None or foreign_keys[0] != 1:
                raise PersistenceOperationalError(
                    "SQLite foreign key enforcement could not be enabled"
                )
            return connection
        except PersistenceOperationalError:
            if connection is not None:
                connection.close()
            raise
        except sqlite3.Error as exc:
            if connection is not None:
                connection.close()
            raise PersistenceOperationalError(
                "Unable to open configured SQLite database"
            ) from exc
