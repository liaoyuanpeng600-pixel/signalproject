"""Deterministic offline filing connector for contract and integration tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.core.sources import Source
from src.core.timestamps import now_utc
from src.ingestion.connector import ConnectorError, ConnectorErrorKind
from src.ingestion.deduplication import content_hash, raw_document_id
from src.ingestion.models import CollectionBatch, IngestionCheckpoint, RawDocument


class FilingFixtureConnector:
    """Load ordered filing records from a local JSON manifest."""

    name = "filing_fixture"
    version = "1.0.0"
    cursor_prefix = "filing-fixture-v1:"

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

        manifest_path = self._manifest_path(source.url)
        records = self._load_manifest(manifest_path)
        start = self._cursor_position(checkpoint.cursor if checkpoint else None)
        selected = records[start : start + limit]
        retrieved_at = now_utc()
        documents = tuple(
            self._to_document(source, manifest_path.parent, item, retrieved_at)
            for item in selected
        )
        next_position = start + len(selected)
        # Preserve the terminal position as well. A committed terminal cursor
        # returns an empty batch instead of re-reading from position zero.
        next_cursor = f"{self.cursor_prefix}{next_position}"
        return CollectionBatch(
            records=documents,
            collected_at=retrieved_at,
            next_cursor=next_cursor,
            provider_run_id=f"{manifest_path.name}:{start}:{next_position}",
        )

    @staticmethod
    def _manifest_path(url: str) -> Path:
        value = url.removeprefix("file://")
        path = Path(value)
        if not path.is_file():
            raise ConnectorError(
                ConnectorErrorKind.CONFIGURATION,
                f"Filing fixture manifest not found: {path}",
                retryable=False,
            )
        return path

    @staticmethod
    def _load_manifest(path: Path) -> list[dict[str, Any]]:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ConnectorError(
                ConnectorErrorKind.MALFORMED_RESPONSE,
                f"Cannot read filing fixture manifest: {path.name}",
                retryable=False,
            ) from exc
        if not isinstance(raw, list) or not all(isinstance(item, dict) for item in raw):
            raise ConnectorError(
                ConnectorErrorKind.MALFORMED_RESPONSE,
                "Filing fixture manifest must be a list of records",
                retryable=False,
            )
        return sorted(raw, key=lambda item: str(item.get("external_id", "")))

    def _cursor_position(self, cursor: str | None) -> int:
        if cursor is None:
            return 0
        if not cursor.startswith(self.cursor_prefix):
            raise ConnectorError(
                ConnectorErrorKind.CONFIGURATION,
                "Invalid filing fixture cursor",
                retryable=False,
            )
        try:
            position = int(cursor.removeprefix(self.cursor_prefix))
        except ValueError as exc:
            raise ConnectorError(
                ConnectorErrorKind.CONFIGURATION,
                "Invalid filing fixture cursor position",
                retryable=False,
            ) from exc
        if position < 0:
            raise ConnectorError(
                ConnectorErrorKind.CONFIGURATION,
                "Filing fixture cursor position must be non-negative",
                retryable=False,
            )
        return position

    def _to_document(
        self,
        source: Source,
        root: Path,
        item: dict[str, Any],
        retrieved_at: str,
    ) -> RawDocument:
        required = ("external_id", "canonical_uri", "published_at", "content_file")
        missing = [name for name in required if not str(item.get(name, "")).strip()]
        if missing:
            raise ConnectorError(
                ConnectorErrorKind.MALFORMED_RESPONSE,
                f"Filing fixture record missing: {', '.join(missing)}",
                retryable=False,
            )
        content_path = root / str(item["content_file"])
        try:
            content = content_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise ConnectorError(
                ConnectorErrorKind.MALFORMED_RESPONSE,
                f"Cannot read filing fixture content: {content_path.name}",
                retryable=False,
            ) from exc
        digest = content_hash(content)
        expected_hash = item.get("expected_content_hash")
        if expected_hash is not None and expected_hash != digest:
            raise ConnectorError(
                ConnectorErrorKind.MALFORMED_RESPONSE,
                f"Filing fixture hash mismatch: {content_path.name}",
                retryable=False,
            )
        external_id = str(item["external_id"])
        metadata_names = ("document_version", "supersedes_external_id")
        metadata = tuple(
            (name, str(item[name]))
            for name in metadata_names
            if item.get(name) is not None
        )
        return RawDocument(
            id=raw_document_id(source.id, external_id),
            source_id=source.id,
            external_id=external_id,
            canonical_uri=str(item["canonical_uri"]),
            published_at=str(item["published_at"]),
            retrieved_at=retrieved_at,
            media_type=str(item.get("media_type", "text/plain")),
            title=str(item["title"]) if item.get("title") is not None else None,
            content=content,
            content_hash=digest,
            raw_payload_ref=str(content_path.resolve()),
            connector_name=self.name,
            connector_version=self.version,
            provider_metadata=metadata,
        )
