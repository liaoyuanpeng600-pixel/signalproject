"""Connector boundary between external providers and ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from src.core.sources import Source
from src.ingestion.models import CollectionBatch, IngestionCheckpoint


class ConnectorErrorKind(str, Enum):
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"
    RATE_LIMITED = "rate_limited"
    AUTHENTICATION = "authentication"
    MALFORMED_RESPONSE = "malformed_response"
    CONFIGURATION = "configuration"
    CONTENT_TOO_LARGE = "content_too_large"
    PERMANENT = "permanent"


class ConnectorError(Exception):
    """A sanitized provider failure suitable for retry policy decisions."""

    def __init__(
        self,
        kind: ConnectorErrorKind,
        message: str,
        *,
        retryable: bool,
        retry_after_seconds: float | None = None,
    ) -> None:
        self.kind = kind
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds
        super().__init__(message)


class Connector(Protocol):
    name: str
    version: str

    def collect(
        self,
        source: Source,
        checkpoint: IngestionCheckpoint | None,
        limit: int,
    ) -> CollectionBatch:
        """Collect a bounded provider-neutral batch."""


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status: int
    body: bytes
    headers: tuple[tuple[str, str], ...] = ()

    def header(self, name: str) -> str | None:
        lowered = name.lower()
        return next(
            (value for key, value in self.headers if key.lower() == lowered),
            None,
        )


class HttpTransport(Protocol):
    def get(self, url: str, *, timeout_seconds: float) -> HttpResponse:
        """Fetch one bounded HTTP response."""
