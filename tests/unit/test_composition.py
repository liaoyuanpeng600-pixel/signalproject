from __future__ import annotations

import ast
import sqlite3
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from src.composition import (
    IngestionComposition,
    SQLiteIngestionConfig,
    compose_sqlite_ingestion,
)
from src.core.sources import Source, SourceType
from src.ingestion.connectors.filing_fixture import FilingFixtureConnector
from src.ingestion.models import (
    CollectionBatch,
    IngestionCheckpoint,
    RawDocument,
    RetryHint,
)
from src.persistence.ingestion import (
    CheckpointConflictError,
    MigrationCompatibilityError,
)

FIXTURES = Path(__file__).parents[1] / "fixtures" / "ingestion" / "filings"


def _source(*, source_id: str = "source-1") -> Source:
    return Source.create(
        type=SourceType.REGULATORY_FILING,
        url=str(FIXTURES / "manifest.json"),
        name="Offline Filing Fixture",
        id=source_id,
    )


def _document(*, source_id: str = "source-1") -> RawDocument:
    return RawDocument(
        id=f"raw-{source_id}",
        source_id=source_id,
        external_id="item-1",
        canonical_uri="https://example.test/item-1",
        published_at="2026-07-25T00:00:00+00:00",
        retrieved_at="2026-07-25T00:01:00+00:00",
        media_type="text/plain",
        content_hash=f"sha256:{'a' * 64}",
        content="bounded content",
        connector_name="controlled",
        connector_version="1.0.0",
    )


class _ControlledConnector:
    name = "controlled"
    version = "1.0.0"

    def __init__(self, batch: CollectionBatch) -> None:
        self.batch = batch

    def collect(
        self,
        source: Source,
        checkpoint: IngestionCheckpoint | None,
        limit: int,
    ) -> CollectionBatch:
        return self.batch


def test_configuration_is_immutable_and_normalizes_path(tmp_path: Path) -> None:
    config = SQLiteIngestionConfig(
        database_path=tmp_path / "signal.sqlite3",
        busy_timeout_ms=123,
        enable_wal=False,
    )

    assert config.database_path == tmp_path / "signal.sqlite3"
    with pytest.raises(FrozenInstanceError):
        config.enable_wal = True  # type: ignore[misc]
    with pytest.raises(ValueError, match="non-negative"):
        SQLiteIngestionConfig(
            database_path=tmp_path / "invalid.sqlite3",
            busy_timeout_ms=-1,
        )


def test_composition_migrates_fresh_database_and_collects_complete_batch(
    tmp_path: Path,
) -> None:
    graph = compose_sqlite_ingestion(
        SQLiteIngestionConfig(tmp_path / "signal.sqlite3")
    )

    result = graph.coordinator.collect(
        connector=FilingFixtureConnector(),
        source=_source(source_id="filing-source"),
        limit=10,
    )

    assert isinstance(graph, IngestionComposition)
    assert not hasattr(graph, "database")
    assert result.documents_inserted == 2
    assert result.document_work_created == 2
    assert result.checkpoint.cursor == "filing-fixture-v1:2"
    assert graph.documents.find_by_collection_identity(
        source_id="filing-source",
        external_id="filing-001",
    ) is not None


def test_empty_complete_batch_creates_checkpoint_without_work(
    tmp_path: Path,
) -> None:
    graph = compose_sqlite_ingestion(
        SQLiteIngestionConfig(tmp_path / "empty.sqlite3")
    )
    batch = CollectionBatch(
        records=(),
        collected_at="2026-07-25T00:02:00+00:00",
        next_cursor="empty:done",
    )

    result = graph.coordinator.collect(
        connector=_ControlledConnector(batch),
        source=_source(),
    )

    assert result.documents_inserted == 0
    assert result.document_work_created == 0
    assert result.checkpoint.cursor == "empty:done"
    assert graph.checkpoints.get("source-1") == result.checkpoint


def test_equivalent_collection_replay_resolves_canonical_rows(
    tmp_path: Path,
) -> None:
    graph = compose_sqlite_ingestion(
        SQLiteIngestionConfig(tmp_path / "replay.sqlite3")
    )
    connector = _ControlledConnector(
        CollectionBatch(
            records=(_document(),),
            collected_at="2026-07-25T00:02:00+00:00",
            next_cursor="controlled:1",
        )
    )

    first = graph.coordinator.collect(
        connector=connector,
        source=_source(),
    )
    replay = graph.coordinator.collect(
        connector=connector,
        source=_source(),
    )

    assert first.documents_inserted == 1
    assert first.document_work_created == 1
    assert replay.documents_inserted == 0
    assert replay.documents_existing == 1
    assert replay.document_work_created == 0
    assert replay.document_work_existing == 1
    assert replay.checkpoint.revision == first.checkpoint.revision + 1


def test_partial_batch_leaves_sqlite_unchanged(tmp_path: Path) -> None:
    graph = compose_sqlite_ingestion(
        SQLiteIngestionConfig(tmp_path / "partial.sqlite3")
    )
    batch = CollectionBatch(
        records=(_document(),),
        is_partial=True,
        retry_hint=RetryHint(retryable=True),
    )

    with pytest.raises(ValueError, match="partial"):
        graph.coordinator.collect(
            connector=_ControlledConnector(batch),
            source=_source(),
        )

    assert graph.documents.get("raw-source-1") is None
    assert graph.checkpoints.get("source-1") is None


def test_checkpoint_race_rolls_back_documents_and_work(tmp_path: Path) -> None:
    graph = compose_sqlite_ingestion(
        SQLiteIngestionConfig(tmp_path / "race.sqlite3")
    )
    batch = CollectionBatch(
        records=(_document(),),
        collected_at="2026-07-25T00:02:00+00:00",
        next_cursor="controlled:1",
    )

    class RacingConnector(_ControlledConnector):
        def collect(
            self,
            source: Source,
            checkpoint: IngestionCheckpoint | None,
            limit: int,
        ) -> CollectionBatch:
            graph.checkpoints.compare_and_set(
                IngestionCheckpoint(
                    source_id=source.id,
                    cursor="racer:1",
                    connector_version=self.version,
                ),
                expected_revision=None,
                connector_name=self.name,
            )
            return self.batch

    with pytest.raises(CheckpointConflictError):
        graph.coordinator.collect(
            connector=RacingConnector(batch),
            source=_source(),
        )

    assert graph.documents.get("raw-source-1") is None
    assert graph.work_items.get("work-raw-source-1") is None
    committed = graph.checkpoints.get("source-1")
    assert committed is not None
    assert committed.cursor == "racer:1"


def test_recomposition_reopens_existing_file_database(tmp_path: Path) -> None:
    config = SQLiteIngestionConfig(tmp_path / "restart.sqlite3")
    first = compose_sqlite_ingestion(config)
    first.coordinator.collect(
        connector=FilingFixtureConnector(),
        source=_source(source_id="filing-source"),
        limit=10,
    )

    restarted = compose_sqlite_ingestion(config)
    document = restarted.documents.find_by_collection_identity(
        source_id="filing-source",
        external_id="filing-001",
    )
    checkpoint = restarted.checkpoints.get("filing-source")

    assert document is not None
    assert checkpoint is not None
    assert checkpoint.cursor == "filing-fixture-v1:2"


def test_migration_compatibility_failure_aborts_composition(
    tmp_path: Path,
) -> None:
    path = tmp_path / "incompatible.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE unexpected (id TEXT PRIMARY KEY)")

    with pytest.raises(MigrationCompatibilityError):
        compose_sqlite_ingestion(SQLiteIngestionConfig(path))


def test_concrete_sqlite_dependency_is_confined_to_composition_root() -> None:
    source_root = Path(__file__).parents[2] / "src"
    violations: list[str] = []

    for path in source_root.rglob("*.py"):
        relative = path.relative_to(source_root)
        if relative == Path("composition.py") or relative.parts[:2] == (
            "persistence",
            "sqlite",
        ):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            modules: tuple[str, ...] = ()
            if isinstance(node, ast.ImportFrom):
                modules = (node.module or "",)
            elif isinstance(node, ast.Import):
                modules = tuple(alias.name for alias in node.names)
            for module in modules:
                if module == "sqlite3" or module.startswith(
                    "src.persistence.sqlite"
                ):
                    violations.append(f"{relative}: {module}")

    assert violations == []
