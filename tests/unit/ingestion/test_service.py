import ast
from pathlib import Path

import pytest

from src.core.sources import Source, SourceType
from src.ingestion.connectors.filing_fixture import FilingFixtureConnector
from src.ingestion.models import CollectionBatch, IngestionCheckpoint
from src.ingestion.service import CollectionRunner

FIXTURES = Path(__file__).parents[2] / "fixtures" / "ingestion" / "filings"


def _source() -> Source:
    return Source.create(
        type=SourceType.REGULATORY_FILING,
        url=str(FIXTURES / "manifest.json"),
        name="Offline Filing Fixture",
        id="filing-source",
    )


def test_deterministic_collection_to_research_handoff() -> None:
    runner = CollectionRunner()
    connector = FilingFixtureConnector()
    source = _source()

    collection_work = runner.prepare_collection_work(
        connector=connector,
        source=source,
        limit=10,
    )
    result = runner.collect(
        connector=connector,
        source=source,
        work_item=collection_work,
    )

    assert result.collection_work_item == collection_work
    assert [record.external_id for record in result.batch.records] == [
        "filing-001",
        "filing-002",
    ]
    assert [
        item.raw_document_id for item in result.document_work_items
    ] == [record.id for record in result.batch.records]

    amendment = result.batch.records[1]
    assert (
        "supersedes_external_id",
        "filing-001",
    ) in amendment.provider_metadata

    # Eligible Signal IDs represent the required upstream Evidence/Signal
    # boundary. The runner does not derive Signals from RawDocuments.
    research_work = runner.prepare_research_work(
        entity_id="entity-1",
        eligible_signal_ids=("signal-2", "signal-1", "signal-1"),
        topic_key="filing-update",
        policy_version="trigger-v1",
    )
    assert research_work.signal_ids == ("signal-1", "signal-2")

    repeated_collection_work = runner.prepare_collection_work(
        connector=connector,
        source=source,
        limit=10,
    )
    repeated_result = runner.collect(
        connector=connector,
        source=source,
        work_item=repeated_collection_work,
    )
    repeated_research_work = runner.prepare_research_work(
        entity_id="entity-1",
        eligible_signal_ids=("signal-1", "signal-2"),
        topic_key="filing-update",
        policy_version="trigger-v1",
    )

    assert repeated_collection_work.id == collection_work.id
    assert repeated_collection_work.idempotency_key == collection_work.idempotency_key
    assert [
        item.id for item in repeated_result.document_work_items
    ] == [item.id for item in result.document_work_items]
    assert repeated_research_work.id == research_work.id
    assert repeated_research_work.idempotency_key == research_work.idempotency_key


def test_known_documents_do_not_create_duplicate_work() -> None:
    runner = CollectionRunner()
    source = _source()
    connector = FilingFixtureConnector()
    work = runner.prepare_collection_work(connector=connector, source=source)
    first = runner.collect(
        connector=connector,
        source=source,
        work_item=work,
    )
    known = frozenset(record.id for record in first.batch.records)
    repeated = runner.collect(
        connector=connector,
        source=source,
        work_item=work,
        known_document_ids=known,
    )
    assert repeated.document_work_items == ()
    assert repeated.deduplication.duplicate_ids == tuple(
        record.id for record in first.batch.records
    )


def test_collection_work_includes_checkpoint_identity() -> None:
    runner = CollectionRunner()
    source = _source()
    connector = FilingFixtureConnector()
    first = runner.prepare_collection_work(connector=connector, source=source)
    checkpoint = IngestionCheckpoint(
        source_id=source.id,
        cursor="filing-fixture-v1:1",
        connector_version=FilingFixtureConnector.version,
        revision=1,
    )
    resumed = runner.prepare_collection_work(
        connector=connector,
        source=source,
        checkpoint=checkpoint,
    )
    assert resumed.id != first.id
    assert resumed.checkpoint == checkpoint


def test_collection_rejects_work_for_another_source() -> None:
    runner = CollectionRunner()
    connector = FilingFixtureConnector()
    work = runner.prepare_collection_work(connector=connector, source=_source())
    other = Source.create(
        type=SourceType.REGULATORY_FILING,
        url=str(FIXTURES / "manifest.json"),
        name="Other",
        id="other-source",
    )
    with pytest.raises(ValueError, match="another Source"):
        runner.collect(
            connector=connector,
            source=other,
            work_item=work,
        )


def test_collection_work_is_bound_to_connector_identity() -> None:
    class OtherConnector:
        name = "other"
        version = "9.0.0"

        def collect(
            self,
            source: Source,
            checkpoint: IngestionCheckpoint | None,
            limit: int,
        ) -> CollectionBatch:
            raise AssertionError("mismatched connector must not execute")

    runner = CollectionRunner()
    connector = FilingFixtureConnector()
    source = _source()
    work = runner.prepare_collection_work(connector=connector, source=source)
    with pytest.raises(ValueError, match="another Connector"):
        runner.collect(
            connector=OtherConnector(),
            source=source,
            work_item=work,
        )


def test_ingestion_dependency_boundary() -> None:
    ingestion_root = Path(__file__).parents[3] / "src" / "ingestion"
    forbidden = {
        "src.persistence",
        "src.runtime",
        "src.reports",
        "src.research",
        "src.core.signals",
        "src.core.evidence",
    }
    violations: list[str] = []
    for path in ingestion_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            module = ""
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if any(
                        alias.name == prefix
                        or alias.name.startswith(f"{prefix}.")
                        for prefix in forbidden
                    ):
                        violations.append(f"{path.name}: {alias.name}")
            if module and any(
                module == prefix or module.startswith(f"{prefix}.")
                for prefix in forbidden
            ):
                violations.append(f"{path.name}: {module}")
    assert violations == []
