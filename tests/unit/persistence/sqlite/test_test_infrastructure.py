from __future__ import annotations

from src.persistence.sqlite import SQLiteDatabase
from tests.contract.persistence.test_checkpoint_repository_contract import (
    CheckpointRepositoryContract,
)
from tests.contract.persistence.test_collection_persistence_contract import (
    CollectionPersistenceContract,
)
from tests.contract.persistence.test_deduplication_repository_contract import (
    DeduplicationRepositoryContract,
)
from tests.contract.persistence.test_document_repository_contract import (
    DocumentRepositoryContract,
)
from tests.contract.persistence.test_work_item_repository_contract import (
    WorkItemRepositoryContract,
)
from tests.unit.persistence.sqlite.contracts import (
    SQLiteContractTestMixin,
    SQLiteIdentityContractTestMixin,
)
from tests.unit.persistence.sqlite.factories import SQLiteTestDatabaseFactory


def test_factory_creates_distinct_initialized_file_databases(
    sqlite_database_factory: SQLiteTestDatabaseFactory,
) -> None:
    first = sqlite_database_factory.create()
    second = sqlite_database_factory.create()

    assert first.path != second.path
    assert first.path.is_file()
    assert second.path.is_file()
    assert str(first.path) != ":memory:"
    assert first.path.suffix == ".sqlite3"


def test_factory_reopens_same_durable_path(
    sqlite_database_factory: SQLiteTestDatabaseFactory,
) -> None:
    original = sqlite_database_factory.create()
    reopened = sqlite_database_factory.reopen(original)

    assert isinstance(reopened, SQLiteDatabase)
    assert reopened is not original
    assert reopened.path == original.path


def test_sqlite_contract_mixin_and_repository_suites_are_reusable() -> None:
    suites = (
        DocumentRepositoryContract,
        CheckpointRepositoryContract,
        DeduplicationRepositoryContract,
        WorkItemRepositoryContract,
        CollectionPersistenceContract,
    )

    assert all(callable(getattr(suite, "create_repository", None)) for suite in suites[:4])
    assert callable(getattr(CollectionPersistenceContract, "create_port", None))
    assert "_set_up_sqlite_contract_database" in vars(SQLiteContractTestMixin)
    assert (
        SQLiteIdentityContractTestMixin.prepare_database
        is not SQLiteContractTestMixin.prepare_database
    )
