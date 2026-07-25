"""Phase 7.1 ingestion application contracts."""

from src.ingestion.connector import (
    Connector,
    ConnectorError,
    ConnectorErrorKind,
    HttpResponse,
    HttpTransport,
)
from src.ingestion.cursor import (
    CheckpointConflictError,
    CursorStore,
    InMemoryCursorStore,
)
from src.ingestion.deduplication import DeduplicationResult, deduplicate_documents
from src.ingestion.models import (
    CollectionBatch,
    IngestionCheckpoint,
    RawDocument,
    RetryHint,
)
from src.ingestion.service import CollectionRunner, CollectionRunResult
from src.ingestion.work import (
    CollectionWorkItem,
    DocumentProcessingWorkItem,
    ResearchWorkItem,
)

__all__ = [
    "CheckpointConflictError",
    "CollectionBatch",
    "CollectionRunResult",
    "CollectionRunner",
    "CollectionWorkItem",
    "Connector",
    "ConnectorError",
    "ConnectorErrorKind",
    "CursorStore",
    "DeduplicationResult",
    "DocumentProcessingWorkItem",
    "HttpResponse",
    "HttpTransport",
    "InMemoryCursorStore",
    "IngestionCheckpoint",
    "RawDocument",
    "ResearchWorkItem",
    "RetryHint",
    "deduplicate_documents",
]
