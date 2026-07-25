from pathlib import Path

import pytest

from src.core.sources import Source, SourceType
from src.ingestion.connector import ConnectorError, ConnectorErrorKind, HttpResponse
from src.ingestion.connectors.rss import RssConnector
from src.ingestion.models import IngestionCheckpoint

FIXTURES = Path(__file__).parents[2] / "fixtures" / "ingestion" / "rss"


class FixtureTransport:
    def __init__(self, response: HttpResponse) -> None:
        self.response = response
        self.calls: list[tuple[str, float]] = []

    def get(self, url: str, *, timeout_seconds: float) -> HttpResponse:
        self.calls.append((url, timeout_seconds))
        return self.response


def _source() -> Source:
    return Source.create(
        type=SourceType.NEWS_ARTICLE,
        url="https://example.com/feed.xml",
        name="Fixture Feed",
        id="rss-source",
    )


def _response(name: str = "rss.xml", status: int = 200) -> HttpResponse:
    body = (FIXTURES / name).read_bytes() if status == 200 else b""
    return HttpResponse(status=status, body=body)


def test_rss_fixture_ingestion() -> None:
    transport = FixtureTransport(_response())
    batch = RssConnector(transport).collect(_source(), None, 10)
    assert [record.external_id for record in batch.records] == ["item-1", "item-2"]
    assert all(record.connector_name == "rss" for record in batch.records)
    assert transport.calls == [("https://example.com/feed.xml", 10.0)]


def test_atom_fixture_ingestion() -> None:
    batch = RssConnector(FixtureTransport(_response("atom.xml"))).collect(
        _source(), None, 10
    )
    assert len(batch.records) == 1
    assert batch.records[0].external_id == "atom-1"
    assert batch.records[0].canonical_uri == "https://example.com/atom-1"


def test_repeated_fetch_has_stable_document_identity() -> None:
    connector = RssConnector(FixtureTransport(_response()))
    first = connector.collect(_source(), None, 10)
    second = connector.collect(_source(), None, 10)
    assert tuple(record.id for record in first.records) == tuple(
        record.id for record in second.records
    )


def test_watermark_filters_processed_entries() -> None:
    connector = RssConnector(FixtureTransport(_response()))
    checkpoint = IngestionCheckpoint(
        source_id="rss-source",
        watermark="2026-07-24T12:00:00+00:00",
        connector_version=connector.version,
    )
    batch = connector.collect(_source(), checkpoint, 10)
    assert [record.external_id for record in batch.records] == ["item-2"]


def test_cursor_paginates_without_repeating_items() -> None:
    connector = RssConnector(FixtureTransport(_response()))
    first = connector.collect(_source(), None, 1)
    assert [record.external_id for record in first.records] == ["item-1"]
    assert first.next_cursor is not None
    checkpoint = IngestionCheckpoint(
        source_id="rss-source",
        cursor=first.next_cursor,
        connector_version=connector.version,
    )
    second = connector.collect(_source(), checkpoint, 1)
    assert [record.external_id for record in second.records] == ["item-2"]
    assert second.next_cursor is not None
    terminal = connector.collect(
        _source(),
        IngestionCheckpoint(
            source_id="rss-source",
            cursor=second.next_cursor,
            connector_version=connector.version,
        ),
        1,
    )
    assert terminal.records == ()


def test_invalid_cursor_is_configuration_error() -> None:
    connector = RssConnector(FixtureTransport(_response()))
    checkpoint = IngestionCheckpoint(
        source_id="rss-source",
        cursor="rss-v0:invalid",
        connector_version=connector.version,
    )
    with pytest.raises(ConnectorError) as caught:
        connector.collect(_source(), checkpoint, 1)
    assert caught.value.kind == ConnectorErrorKind.CONFIGURATION


def test_not_modified_returns_empty_success() -> None:
    batch = RssConnector(FixtureTransport(_response(status=304))).collect(
        _source(), None, 10
    )
    assert batch.records == ()


def test_rate_limit_is_typed() -> None:
    response = HttpResponse(
        status=429, body=b"", headers=(("Retry-After", "30"),)
    )
    with pytest.raises(ConnectorError) as caught:
        RssConnector(FixtureTransport(response)).collect(_source(), None, 10)
    assert caught.value.kind == ConnectorErrorKind.RATE_LIMITED
    assert caught.value.retry_after_seconds == 30


def test_malformed_feed_is_rejected() -> None:
    with pytest.raises(ConnectorError) as caught:
        RssConnector(FixtureTransport(_response("malformed.xml"))).collect(
            _source(), None, 10
        )
    assert caught.value.kind == ConnectorErrorKind.MALFORMED_RESPONSE
