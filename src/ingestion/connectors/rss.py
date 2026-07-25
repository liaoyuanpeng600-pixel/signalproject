"""RSS/Atom connector with an injectable HTTP transport."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import socket
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from src.core.sources import Source
from src.core.timestamps import now_utc
from src.ingestion.connector import (
    ConnectorError,
    ConnectorErrorKind,
    HttpResponse,
    HttpTransport,
)
from src.ingestion.deduplication import content_hash, raw_document_id
from src.ingestion.models import CollectionBatch, IngestionCheckpoint, RawDocument


@dataclass(frozen=True, slots=True)
class _FeedEntry:
    external_id: str
    uri: str
    published_at: str
    title: str | None
    content: str


class UrllibHttpTransport:
    """Small standard-library transport kept outside connector mapping logic."""

    def __init__(
        self,
        *,
        user_agent: str = "SignalProject/0.1 ingestion",
        max_response_bytes: int = 5_000_000,
    ) -> None:
        self._user_agent = user_agent
        self._max_response_bytes = max_response_bytes

    def get(self, url: str, *, timeout_seconds: float) -> HttpResponse:
        request = urllib.request.Request(url, headers={"User-Agent": self._user_agent})
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                body = response.read(self._max_response_bytes + 1)
                if len(body) > self._max_response_bytes:
                    raise ConnectorError(
                        ConnectorErrorKind.CONTENT_TOO_LARGE,
                        "RSS response exceeded configured size limit",
                        retryable=False,
                    )
                return HttpResponse(
                    status=response.status,
                    body=body,
                    headers=tuple(response.headers.items()),
                )
        except urllib.error.HTTPError as exc:
            return HttpResponse(
                status=exc.code,
                body=exc.read(self._max_response_bytes),
                headers=tuple(exc.headers.items()) if exc.headers else (),
            )
        except (TimeoutError, socket.timeout) as exc:
            raise ConnectorError(
                ConnectorErrorKind.TIMEOUT,
                "RSS request timed out",
                retryable=True,
            ) from exc
        except urllib.error.URLError as exc:
            raise ConnectorError(
                ConnectorErrorKind.UNAVAILABLE,
                "RSS source is unavailable",
                retryable=True,
            ) from exc


class RssConnector:
    name = "rss"
    version = "1.0.0"

    def __init__(
        self,
        transport: HttpTransport | None = None,
        *,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._transport = transport or UrllibHttpTransport()
        self._timeout_seconds = timeout_seconds

    def collect(
        self,
        source: Source,
        checkpoint: IngestionCheckpoint | None,
        limit: int,
    ) -> CollectionBatch:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if checkpoint is not None:
            if checkpoint.source_id != source.id:
                raise ConnectorError(
                    ConnectorErrorKind.CONFIGURATION,
                    "Checkpoint belongs to another Source",
                    retryable=False,
                )
            if checkpoint.connector_version != self.version:
                raise ConnectorError(
                    ConnectorErrorKind.CONFIGURATION,
                    "Checkpoint connector version is incompatible",
                    retryable=False,
                )

        response = self._transport.get(
            source.url, timeout_seconds=self._timeout_seconds
        )
        if response.status == 304:
            return CollectionBatch(records=(), collected_at=now_utc())
        if response.status == 429:
            retry_after = self._retry_after(response.header("Retry-After"))
            raise ConnectorError(
                ConnectorErrorKind.RATE_LIMITED,
                "RSS provider rate limited the request",
                retryable=True,
                retry_after_seconds=retry_after,
            )
        if response.status in {401, 403}:
            raise ConnectorError(
                ConnectorErrorKind.AUTHENTICATION,
                "RSS provider rejected authentication",
                retryable=False,
            )
        if response.status >= 500:
            raise ConnectorError(
                ConnectorErrorKind.UNAVAILABLE,
                f"RSS provider returned HTTP {response.status}",
                retryable=True,
            )
        if response.status < 200 or response.status >= 300:
            raise ConnectorError(
                ConnectorErrorKind.PERMANENT,
                f"RSS provider returned HTTP {response.status}",
                retryable=False,
            )

        entries = self._parse(response.body, source.url)
        watermark = checkpoint.watermark if checkpoint else None
        if watermark is not None:
            entries = [entry for entry in entries if entry.published_at > watermark]
        cursor_position = self._decode_cursor(
            checkpoint.cursor if checkpoint is not None else None
        )
        if cursor_position is not None:
            entries = [
                entry
                for entry in entries
                if (entry.published_at, entry.external_id) > cursor_position
            ]
        entries.sort(key=lambda entry: (entry.published_at, entry.external_id))
        selected = entries[:limit]
        retrieved_at = now_utc()
        documents = tuple(
            RawDocument(
                id=raw_document_id(source.id, entry.external_id),
                source_id=source.id,
                external_id=entry.external_id,
                canonical_uri=entry.uri,
                published_at=entry.published_at,
                retrieved_at=retrieved_at,
                media_type="application/xml+rss",
                title=entry.title,
                content=entry.content,
                content_hash=content_hash(entry.content),
                connector_name=self.name,
                connector_version=self.version,
            )
            for entry in selected
        )
        next_cursor = (
            self._encode_cursor(selected[-1])
            if selected
            else (checkpoint.cursor if checkpoint is not None else None)
        )
        return CollectionBatch(
            records=documents,
            collected_at=retrieved_at,
            next_cursor=next_cursor,
            provider_run_id=response.header("X-Request-ID"),
        )

    def _parse(self, body: bytes, feed_url: str) -> list[_FeedEntry]:
        try:
            root = ET.fromstring(body)
        except ET.ParseError as exc:
            raise ConnectorError(
                ConnectorErrorKind.MALFORMED_RESPONSE,
                "RSS response is not valid XML",
                retryable=False,
            ) from exc
        root_name = self._local_name(root.tag)
        if root_name == "rss":
            elements = root.findall("./channel/item")
        elif root_name == "feed":
            elements = [
                element
                for element in list(root)
                if self._local_name(element.tag) == "entry"
            ]
        else:
            raise ConnectorError(
                ConnectorErrorKind.MALFORMED_RESPONSE,
                "Unsupported RSS/Atom root element",
                retryable=False,
            )
        return [self._parse_entry(element, feed_url) for element in elements]

    def _parse_entry(self, element: ET.Element, feed_url: str) -> _FeedEntry:
        values = {
            self._local_name(child.tag): (child.text or "").strip()
            for child in list(element)
            if self._local_name(child.tag) != "link"
        }
        link = self._entry_link(element)
        title = values.get("title") or None
        content = values.get("content") or values.get("description") or values.get(
            "summary"
        )
        if not content:
            raise ConnectorError(
                ConnectorErrorKind.MALFORMED_RESPONSE,
                "RSS entry has no content or summary",
                retryable=False,
            )
        raw_date = (
            values.get("published")
            or values.get("pubDate")
            or values.get("updated")
        )
        if not raw_date:
            raise ConnectorError(
                ConnectorErrorKind.MALFORMED_RESPONSE,
                "RSS entry has no publication timestamp",
                retryable=False,
            )
        published_at = self._normalize_date(raw_date)
        external_id = values.get("guid") or values.get("id") or link
        if not external_id:
            payload = f"rss-fallback-v1\0{feed_url}\0{title}\0{published_at}\0{content}"
            external_id = f"generated:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"
        return _FeedEntry(
            external_id=external_id,
            uri=link or feed_url,
            published_at=published_at,
            title=title,
            content=content,
        )

    @staticmethod
    def _entry_link(element: ET.Element) -> str:
        for child in list(element):
            if RssConnector._local_name(child.tag) != "link":
                continue
            href = child.attrib.get("href", "").strip()
            if href:
                return href
            if child.text and child.text.strip():
                return child.text.strip()
        return ""

    @staticmethod
    def _local_name(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    @staticmethod
    def _normalize_date(value: str) -> str:
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
            try:
                parsed = datetime.fromisoformat(normalized)
            except ValueError as exc:
                raise ConnectorError(
                    ConnectorErrorKind.MALFORMED_RESPONSE,
                    "RSS entry has an invalid publication timestamp",
                    retryable=False,
                ) from exc
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _retry_after(value: str | None) -> float | None:
        if value is None:
            return None
        try:
            return max(0.0, float(value))
        except ValueError:
            return None

    @staticmethod
    def _encode_cursor(entry: _FeedEntry) -> str:
        payload = json.dumps(
            [entry.published_at, entry.external_id],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        encoded = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
        return f"rss-v1:{encoded}"

    @staticmethod
    def _decode_cursor(cursor: str | None) -> tuple[str, str] | None:
        if cursor is None:
            return None
        prefix = "rss-v1:"
        if not cursor.startswith(prefix):
            raise ConnectorError(
                ConnectorErrorKind.CONFIGURATION,
                "Invalid RSS cursor version",
                retryable=False,
            )
        encoded = cursor.removeprefix(prefix)
        try:
            padding = "=" * (-len(encoded) % 4)
            decoded = base64.urlsafe_b64decode(encoded + padding)
            value = json.loads(decoded.decode("utf-8"))
        except (ValueError, UnicodeError, binascii.Error) as exc:
            raise ConnectorError(
                ConnectorErrorKind.CONFIGURATION,
                "Invalid RSS cursor payload",
                retryable=False,
            ) from exc
        if (
            not isinstance(value, list)
            or len(value) != 2
            or not all(isinstance(part, str) and part for part in value)
        ):
            raise ConnectorError(
                ConnectorErrorKind.CONFIGURATION,
                "Invalid RSS cursor position",
                retryable=False,
            )
        return value[0], value[1]
