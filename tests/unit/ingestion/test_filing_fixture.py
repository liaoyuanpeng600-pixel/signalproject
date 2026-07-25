from pathlib import Path

import pytest

from src.core.sources import Source, SourceType
from src.ingestion.connector import ConnectorError
from src.ingestion.connectors.filing_fixture import FilingFixtureConnector
from src.ingestion.models import IngestionCheckpoint

FIXTURES = Path(__file__).parents[2] / "fixtures" / "ingestion" / "filings"


def _source(manifest: str = "manifest.json") -> Source:
    return Source.create(
        type=SourceType.REGULATORY_FILING,
        url=str(FIXTURES / manifest),
        name="Offline Filing Fixture",
        id="filing-source",
    )


def test_filing_fixture_is_deterministic() -> None:
    connector = FilingFixtureConnector()
    first = connector.collect(_source(), None, 10)
    second = connector.collect(_source(), None, 10)
    assert tuple(record.id for record in first.records) == tuple(
        record.id for record in second.records
    )
    assert tuple(record.content_hash for record in first.records) == tuple(
        record.content_hash for record in second.records
    )


def test_filing_fixture_paginates_with_opaque_cursor() -> None:
    connector = FilingFixtureConnector()
    first = connector.collect(_source(), None, 1)
    assert len(first.records) == 1
    assert first.next_cursor is not None
    checkpoint = IngestionCheckpoint(
        source_id="filing-source",
        cursor=first.next_cursor,
        connector_version=connector.version,
    )
    second = connector.collect(_source(), checkpoint, 1)
    assert len(second.records) == 1
    assert second.records[0].id != first.records[0].id
    assert second.next_cursor is not None
    terminal = connector.collect(
        _source(),
        IngestionCheckpoint(
            source_id="filing-source",
            cursor=second.next_cursor,
            connector_version=connector.version,
        ),
        1,
    )
    assert terminal.records == ()


def test_filing_fixture_preserves_revision_metadata() -> None:
    batch = FilingFixtureConnector().collect(_source(), None, 10)
    amendment = next(record for record in batch.records if record.external_id == "filing-002")
    assert ("supersedes_external_id", "filing-001") in amendment.provider_metadata


def test_missing_manifest_is_configuration_error() -> None:
    with pytest.raises(ConnectorError):
        FilingFixtureConnector().collect(_source("missing.json"), None, 10)


def test_malformed_manifest_is_rejected() -> None:
    with pytest.raises(ConnectorError):
        FilingFixtureConnector().collect(_source("malformed.json"), None, 10)
