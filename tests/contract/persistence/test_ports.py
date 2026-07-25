import ast
import inspect
from pathlib import Path

from src.persistence.ingestion import (
    CheckpointConflictError,
    CheckpointRepository,
    CollectionPersistencePort,
    DeduplicationRepository,
    DocumentConflictError,
    DocumentRepository,
    IdentityConflictError,
    MigrationCompatibilityError,
    PayloadCompatibilityError,
    PersistenceError,
    PersistenceOperationalError,
    WorkItemConflictError,
    WorkItemRepository,
)


def test_persistence_errors_have_one_stable_base() -> None:
    error_types = (
        PersistenceOperationalError,
        DocumentConflictError,
        IdentityConflictError,
        CheckpointConflictError,
        WorkItemConflictError,
        PayloadCompatibilityError,
        MigrationCompatibilityError,
    )

    assert all(issubclass(error_type, PersistenceError) for error_type in error_types)


def test_repository_ports_are_protocols() -> None:
    ports = (
        DocumentRepository,
        CheckpointRepository,
        DeduplicationRepository,
        WorkItemRepository,
        CollectionPersistencePort,
    )

    assert all(getattr(port, "_is_protocol", False) for port in ports)


def test_work_repository_is_pending_persistence_only() -> None:
    forbidden = {
        "claim",
        "lease",
        "start",
        "complete",
        "fail",
        "retry",
        "dead_letter",
        "increment_attempt",
    }

    assert forbidden.isdisjoint(vars(WorkItemRepository))
    assert set(vars(WorkItemRepository)) >= {"insert", "get"}


def test_checkpoint_creation_revision_is_explicit() -> None:
    signature = inspect.signature(CheckpointRepository.compare_and_set)

    expected = signature.parameters["expected_revision"]
    assert expected.default is inspect.Parameter.empty
    assert expected.kind is inspect.Parameter.KEYWORD_ONLY


def test_atomic_port_exposes_no_transaction_argument() -> None:
    signature = inspect.signature(CollectionPersistencePort.commit_collection)

    assert tuple(signature.parameters) == ("self", "command")


def test_persistence_contract_dependency_boundary() -> None:
    root = Path(__file__).parents[3] / "src" / "persistence" / "ingestion"
    forbidden = {
        "sqlite3",
        "src.runtime",
        "src.research",
        "src.reports",
        "src.ingestion.connectors",
    }
    violations: list[str] = []

    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            modules: tuple[str, ...] = ()
            if isinstance(node, ast.ImportFrom):
                modules = (node.module or "",)
            elif isinstance(node, ast.Import):
                modules = tuple(alias.name for alias in node.names)
            for module in modules:
                if any(
                    module == prefix or module.startswith(f"{prefix}.")
                    for prefix in forbidden
                ):
                    violations.append(f"{path.name}: {module}")

    assert violations == []


def test_ingestion_does_not_reverse_import_persistence() -> None:
    root = Path(__file__).parents[3] / "src" / "ingestion"
    violations: list[str] = []

    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module == "src.persistence" or module.startswith("src.persistence."):
                    violations.append(f"{path.name}: {module}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "src.persistence" or alias.name.startswith(
                        "src.persistence."
                    ):
                        violations.append(f"{path.name}: {alias.name}")

    assert violations == []
