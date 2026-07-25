"""SQLite adapter for pending typed ingestion work."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from typing import Any

from src.core.ids import ID
from src.ingestion.models import IngestionCheckpoint
from src.ingestion.work import (
    CollectionWorkItem,
    DocumentProcessingWorkItem,
    ResearchWorkItem,
)
from src.persistence.ingestion.errors import (
    PayloadCompatibilityError,
    PersistenceError,
    PersistenceOperationalError,
    WorkItemConflictError,
)
from src.persistence.ingestion.models import (
    IngestionWorkItem,
    WorkInsertDisposition,
    WorkInsertResult,
)
from src.persistence.sqlite.database import SQLiteDatabase

_PAYLOAD_SCHEMA_VERSION = "1.0.0"
_COLLECTION_KIND = "collection"
_DOCUMENT_PROCESSING_KIND = "document_processing"
_RESEARCH_KIND = "research"
_SUPPORTED_KINDS = {
    _COLLECTION_KIND,
    _DOCUMENT_PROCESSING_KIND,
    _RESEARCH_KIND,
}
_WORK_ITEM_COLUMNS = """
    id,
    kind,
    payload_json,
    payload_schema_version,
    idempotency_key,
    created_at
"""


class SQLiteWorkItemRepository:
    """Persist and retrieve pending Phase 7.1 typed work."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def insert(self, work_item: IngestionWorkItem) -> WorkInsertResult:
        """Insert or resolve an equivalent idempotent work item."""

        _validate_work_item(work_item)
        try:
            with self._database.transaction() as connection:
                return _insert_or_resolve_work_item(connection, work_item)
        except PersistenceError:
            raise
        except sqlite3.Error as exc:
            raise PersistenceOperationalError(
                "SQLite work item insertion failed"
            ) from exc

    def get(self, work_item_id: ID) -> IngestionWorkItem | None:
        """Return one typed work item by its application-owned ID."""

        try:
            with self._database.connection() as connection:
                return _get_work_item(connection, work_item_id)
        except PersistenceError:
            raise
        except sqlite3.Error as exc:
            raise PersistenceOperationalError(
                "SQLite work item retrieval failed"
            ) from exc


def _insert_or_resolve_work_item(
    connection: sqlite3.Connection,
    work_item: IngestionWorkItem,
) -> WorkInsertResult:
    """Connection-scoped insert for future atomic collection persistence."""

    kind = _work_item_kind(work_item)
    payload_json = _encode_work_item_payload(work_item)
    try:
        connection.execute(
            """
            INSERT INTO work_items (
                id,
                kind,
                payload_json,
                payload_schema_version,
                idempotency_key,
                status,
                priority,
                available_at,
                created_at,
                updated_at,
                revision
            ) VALUES (?, ?, ?, ?, ?, 'pending', 50, ?, ?, ?, 0)
            """,
            (
                work_item.id,
                kind,
                payload_json,
                _PAYLOAD_SCHEMA_VERSION,
                work_item.idempotency_key,
                work_item.created_at,
                work_item.created_at,
                work_item.created_at,
            ),
        )
    except sqlite3.IntegrityError as exc:
        return _resolve_work_item_conflict(connection, work_item, exc)

    stored = _get_work_item(connection, work_item.id)
    if stored is None:
        raise PersistenceOperationalError(
            "Inserted SQLite work item could not be reloaded"
        )
    return WorkInsertResult(
        work_item=stored,
        disposition=WorkInsertDisposition.INSERTED,
    )


def _resolve_work_item_conflict(
    connection: sqlite3.Connection,
    work_item: IngestionWorkItem,
    cause: sqlite3.IntegrityError,
) -> WorkInsertResult:
    kind = _work_item_kind(work_item)
    by_id = _get_work_item(connection, work_item.id)
    by_identity = _find_work_item_by_identity(
        connection,
        kind=kind,
        idempotency_key=work_item.idempotency_key,
    )

    if (
        by_id is not None
        and by_identity is not None
        and by_id.id != by_identity.id
    ):
        raise WorkItemConflictError(
            "Work item ID and idempotency identity resolve to different work"
        ) from cause

    existing = by_id or by_identity
    if existing is None:
        raise PersistenceOperationalError(
            "SQLite work item insertion violated an unexpected constraint"
        ) from cause
    if (
        _work_item_kind(existing) != kind
        or existing.idempotency_key != work_item.idempotency_key
    ):
        raise WorkItemConflictError(
            "Application-owned work item ID cannot be rebound"
        ) from cause
    if _encode_work_item_payload(existing) != _encode_work_item_payload(work_item):
        raise WorkItemConflictError(
            "Work idempotency identity has a different canonical payload"
        ) from cause
    return WorkInsertResult(
        work_item=existing,
        disposition=WorkInsertDisposition.EXISTING,
    )


def _get_work_item(
    connection: sqlite3.Connection,
    work_item_id: ID,
) -> IngestionWorkItem | None:
    row = connection.execute(
        f"""
        SELECT {_WORK_ITEM_COLUMNS}
        FROM work_items
        WHERE id = ?
        """,
        (work_item_id,),
    ).fetchone()
    return _row_to_work_item(row) if row is not None else None


def _find_work_item_by_identity(
    connection: sqlite3.Connection,
    *,
    kind: str,
    idempotency_key: str,
) -> IngestionWorkItem | None:
    row = connection.execute(
        f"""
        SELECT {_WORK_ITEM_COLUMNS}
        FROM work_items
        WHERE kind = ? AND idempotency_key = ?
        """,
        (kind, idempotency_key),
    ).fetchone()
    return _row_to_work_item(row) if row is not None else None


def _row_to_work_item(row: sqlite3.Row) -> IngestionWorkItem:
    kind = _read_text(row, "kind")
    schema_version = _read_text(row, "payload_schema_version")
    if schema_version != _PAYLOAD_SCHEMA_VERSION:
        raise PayloadCompatibilityError(
            "Stored work item payload schema version is unsupported"
        )
    if kind not in _SUPPORTED_KINDS:
        raise PayloadCompatibilityError("Stored work item kind is unsupported")

    payload = _decode_payload_json(_read_text(row, "payload_json"))
    work_item_id = ID(_read_text(row, "id"))
    idempotency_key = _read_text(row, "idempotency_key")
    created_at = _read_text(row, "created_at")
    try:
        if kind == _COLLECTION_KIND:
            _require_exact_keys(
                payload,
                {
                    "source_id",
                    "connector_name",
                    "connector_version",
                    "checkpoint",
                    "limit",
                },
            )
            checkpoint_value = payload["checkpoint"]
            checkpoint = (
                None
                if checkpoint_value is None
                else _decode_checkpoint(checkpoint_value)
            )
            return CollectionWorkItem(
                source_id=ID(_require_string(payload, "source_id")),
                connector_name=_require_string(payload, "connector_name"),
                connector_version=_require_string(payload, "connector_version"),
                checkpoint=checkpoint,
                limit=_require_integer(payload, "limit"),
                id=work_item_id,
                idempotency_key=idempotency_key,
                created_at=created_at,
                schema_version=schema_version,
            )
        if kind == _DOCUMENT_PROCESSING_KIND:
            _require_exact_keys(payload, {"document_id"})
            return DocumentProcessingWorkItem(
                raw_document_id=ID(_require_string(payload, "document_id")),
                id=work_item_id,
                idempotency_key=idempotency_key,
                created_at=created_at,
                schema_version=schema_version,
            )

        _require_exact_keys(
            payload,
            {"entity_id", "signal_ids", "topic_key"},
        )
        signal_values = payload["signal_ids"]
        if not isinstance(signal_values, list) or not all(
            isinstance(value, str) for value in signal_values
        ):
            raise PayloadCompatibilityError(
                "Research work signal_ids payload is incompatible"
            )
        return ResearchWorkItem(
            entity_id=ID(_require_string(payload, "entity_id")),
            signal_ids=tuple(ID(value) for value in signal_values),
            topic_key=_require_string(payload, "topic_key"),
            id=work_item_id,
            idempotency_key=idempotency_key,
            created_at=created_at,
            schema_version=schema_version,
        )
    except PayloadCompatibilityError:
        raise
    except (TypeError, ValueError) as exc:
        raise PayloadCompatibilityError(
            "Stored work item payload is incompatible with its typed DTO"
        ) from exc


def _encode_work_item_payload(work_item: IngestionWorkItem) -> str:
    if isinstance(work_item, CollectionWorkItem):
        payload: dict[str, Any] = {
            "source_id": str(work_item.source_id),
            "connector_name": work_item.connector_name,
            "connector_version": work_item.connector_version,
            "checkpoint": (
                _encode_checkpoint(work_item.checkpoint)
                if work_item.checkpoint is not None
                else None
            ),
            "limit": work_item.limit,
        }
    elif isinstance(work_item, DocumentProcessingWorkItem):
        payload = {"document_id": str(work_item.raw_document_id)}
    elif isinstance(work_item, ResearchWorkItem):
        payload = {
            "entity_id": str(work_item.entity_id),
            "signal_ids": sorted(
                (str(signal_id) for signal_id in work_item.signal_ids)
            ),
            "topic_key": work_item.topic_key,
        }
    else:
        raise PayloadCompatibilityError("Work item kind is unsupported")
    return _canonical_json(payload)


def _encode_checkpoint(checkpoint: IngestionCheckpoint) -> dict[str, Any]:
    return {
        "source_id": str(checkpoint.source_id),
        "cursor": checkpoint.cursor,
        "watermark": checkpoint.watermark,
        "last_success_at": checkpoint.last_success_at,
        "connector_version": checkpoint.connector_version,
        "revision": checkpoint.revision,
        "schema_version": checkpoint.schema_version,
    }


def _decode_checkpoint(value: object) -> IngestionCheckpoint:
    if not isinstance(value, dict):
        raise PayloadCompatibilityError(
            "Collection checkpoint payload must be an object or null"
        )
    _require_exact_keys(
        value,
        {
            "source_id",
            "cursor",
            "watermark",
            "last_success_at",
            "connector_version",
            "revision",
            "schema_version",
        },
    )
    return IngestionCheckpoint(
        source_id=ID(_require_string(value, "source_id")),
        cursor=_require_optional_string(value, "cursor"),
        watermark=_require_optional_string(value, "watermark"),
        last_success_at=_require_optional_string(value, "last_success_at"),
        connector_version=_require_string(value, "connector_version"),
        revision=_require_integer(value, "revision"),
        schema_version=_require_string(value, "schema_version"),
    )


def _decode_payload_json(value: str) -> dict[str, Any]:
    try:
        decoded = json.loads(value)
    except (TypeError, json.JSONDecodeError) as exc:
        raise PayloadCompatibilityError(
            "Stored work item payload is not valid JSON"
        ) from exc
    if not isinstance(decoded, dict):
        raise PayloadCompatibilityError(
            "Stored work item payload must be a JSON object"
        )
    return decoded


def _canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _work_item_kind(work_item: IngestionWorkItem) -> str:
    if isinstance(work_item, CollectionWorkItem):
        return _COLLECTION_KIND
    if isinstance(work_item, DocumentProcessingWorkItem):
        return _DOCUMENT_PROCESSING_KIND
    if isinstance(work_item, ResearchWorkItem):
        return _RESEARCH_KIND
    raise PayloadCompatibilityError("Work item kind is unsupported")


def _validate_work_item(work_item: IngestionWorkItem) -> None:
    _work_item_kind(work_item)
    if work_item.schema_version != _PAYLOAD_SCHEMA_VERSION:
        raise PayloadCompatibilityError(
            "Work item payload schema version is unsupported"
        )


def _read_text(row: sqlite3.Row, key: str) -> str:
    try:
        value = row[key]
    except IndexError as exc:
        raise PersistenceOperationalError(
            "Stored SQLite work item row is incomplete"
        ) from exc
    if not isinstance(value, str):
        raise PayloadCompatibilityError(
            "Stored work item text field is incompatible"
        )
    return value


def _require_exact_keys(
    value: Mapping[str, object],
    expected: set[str],
) -> None:
    if set(value) != expected:
        raise PayloadCompatibilityError(
            "Stored work item payload fields are incompatible"
        )


def _require_string(value: Mapping[str, object], key: str) -> str:
    field = value[key]
    if not isinstance(field, str):
        raise PayloadCompatibilityError(
            "Stored work item payload contains a non-string field"
        )
    return field


def _require_optional_string(
    value: Mapping[str, object],
    key: str,
) -> str | None:
    field = value[key]
    if field is not None and not isinstance(field, str):
        raise PayloadCompatibilityError(
            "Stored work item payload contains an invalid optional string"
        )
    return field


def _require_integer(value: Mapping[str, object], key: str) -> int:
    field = value[key]
    if not isinstance(field, int) or isinstance(field, bool):
        raise PayloadCompatibilityError(
            "Stored work item payload contains a non-integer field"
        )
    return field
