"""Provider-neutral application models for Phase 7.1 ingestion."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from src.core.ids import ID
from src.core.timestamps import now_utc

RAW_DOCUMENT_SCHEMA_VERSION = "1.0.0"
COLLECTION_BATCH_SCHEMA_VERSION = "1.0.0"
CHECKPOINT_SCHEMA_VERSION = "1.0.0"


def _validate_timestamp(value: str, field_name: str) -> None:
    if not value:
        raise ValueError(f"{field_name} is required")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must include a timezone")


@dataclass(frozen=True, slots=True)
class RetryHint:
    """Provider-neutral advice for a later collection attempt."""

    retryable: bool
    retry_after_seconds: float | None = None
    reason: str = ""

    def __post_init__(self) -> None:
        if self.retry_after_seconds is not None and self.retry_after_seconds < 0:
            raise ValueError("retry_after_seconds must be non-negative")


@dataclass(frozen=True, slots=True)
class RawDocument:
    """A provider-neutral collected document, before Evidence production."""

    id: ID
    source_id: ID
    external_id: str
    canonical_uri: str
    published_at: str
    retrieved_at: str
    media_type: str
    content_hash: str
    content: str | None = None
    title: str | None = None
    raw_payload_ref: str | None = None
    connector_name: str = ""
    connector_version: str = ""
    provider_metadata: tuple[tuple[str, str], ...] = ()
    schema_version: str = RAW_DOCUMENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "id",
            "source_id",
            "external_id",
            "canonical_uri",
            "media_type",
            "content_hash",
            "connector_name",
            "connector_version",
            "schema_version",
        ):
            if not getattr(self, name):
                raise ValueError(f"RawDocument.{name} is required")
        _validate_timestamp(self.published_at, "RawDocument.published_at")
        _validate_timestamp(self.retrieved_at, "RawDocument.retrieved_at")
        if self.content is None and self.raw_payload_ref is None:
            raise ValueError("RawDocument requires content or raw_payload_ref")
        if self.content_hash.startswith("sha256:"):
            digest = self.content_hash.removeprefix("sha256:")
        else:
            digest = self.content_hash
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest.lower()):
            raise ValueError("RawDocument.content_hash must contain a SHA-256 hex digest")


@dataclass(frozen=True, slots=True)
class CollectionBatch:
    """A bounded connector result with an opaque continuation cursor."""

    records: tuple[RawDocument, ...]
    collected_at: str = field(default_factory=now_utc)
    next_cursor: str | None = None
    provider_run_id: str | None = None
    is_partial: bool = False
    retry_hint: RetryHint | None = None
    schema_version: str = COLLECTION_BATCH_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _validate_timestamp(self.collected_at, "CollectionBatch.collected_at")
        if not self.schema_version:
            raise ValueError("CollectionBatch.schema_version is required")
        ids = [str(record.id) for record in self.records]
        if len(ids) != len(set(ids)):
            raise ValueError("CollectionBatch contains duplicate document IDs")
        if self.is_partial and self.retry_hint is None:
            raise ValueError("A partial CollectionBatch requires a retry_hint")


@dataclass(frozen=True, slots=True)
class IngestionCheckpoint:
    """Persistence-neutral progress for one Source and Connector version."""

    source_id: ID
    cursor: str | None = None
    watermark: str | None = None
    last_success_at: str | None = None
    connector_version: str = ""
    revision: int = 0
    schema_version: str = CHECKPOINT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.source_id:
            raise ValueError("IngestionCheckpoint.source_id is required")
        if not self.connector_version:
            raise ValueError("IngestionCheckpoint.connector_version is required")
        if self.revision < 0:
            raise ValueError("IngestionCheckpoint.revision must be non-negative")
        if self.watermark is not None:
            _validate_timestamp(self.watermark, "IngestionCheckpoint.watermark")
        if self.last_success_at is not None:
            _validate_timestamp(
                self.last_success_at, "IngestionCheckpoint.last_success_at"
            )
