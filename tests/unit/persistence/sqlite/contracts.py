"""Shared pytest setup for future concrete SQLite repository contract suites."""

from __future__ import annotations

import pytest

from src.persistence.sqlite import SQLiteDatabase
from tests.unit.persistence.sqlite.factories import SQLiteTestDatabaseFactory


class SQLiteContractTestMixin:
    """Give inherited repository contract tests one initialized file database."""

    database: SQLiteDatabase

    @pytest.fixture(autouse=True)
    def _set_up_sqlite_contract_database(
        self,
        sqlite_database_factory: SQLiteTestDatabaseFactory,
    ) -> None:
        self.database = sqlite_database_factory.create()
        self.prepare_database()

    def prepare_database(self) -> None:
        """Hook for contract suites that require referenced fixture rows."""


class SQLiteIdentityContractTestMixin(SQLiteContractTestMixin):
    """Seed documents referenced by the reusable identity repository contract."""

    def prepare_database(self) -> None:
        with self.database.transaction() as connection:
            for document_id, external_id in (
                ("raw-1", "item-1"),
                ("raw-2", "item-2"),
            ):
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
