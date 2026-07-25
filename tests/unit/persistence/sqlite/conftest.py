"""Fixtures for SQLite persistence adapter tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.persistence.sqlite import SQLiteDatabase
from tests.unit.persistence.sqlite.factories import SQLiteTestDatabaseFactory


@pytest.fixture
def sqlite_database_factory(tmp_path: Path) -> SQLiteTestDatabaseFactory:
    return SQLiteTestDatabaseFactory(tmp_path)


@pytest.fixture
def sqlite_database(
    sqlite_database_factory: SQLiteTestDatabaseFactory,
) -> SQLiteDatabase:
    return sqlite_database_factory.create()
