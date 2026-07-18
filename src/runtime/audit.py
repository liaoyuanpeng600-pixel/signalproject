"""
AuditLogger — append-only event log for the Runtime layer.

Per Runtime Model §"Audit Logging":
- All events are recorded in the audit log
- The log is immutable and append-only
- Every gate evaluation, state transition, retry attempt, and failure is logged
- Audit entries contain: cycle_id, component, event type, result, timestamp

For Phase 3 (MVP), the AuditLogger is in-memory only. Phase 4 (Persistence)
will provide a persistent backend; the interface is designed to be
storage-agnostic.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class EventCategory(str, Enum):
    """Category of an audit event."""

    CYCLE = "cycle"
    STAGE = "stage"
    GATE = "gate"
    OBJECT = "object"
    RETRY = "retry"
    FAILURE = "failure"


@dataclass(frozen=True)
class AuditRecord:
    """A single immutable audit log entry.

    Per Runtime Model §"Log Entry Structure":
    - Timestamp
    - Cycle ID
    - Component (which runtime component produced the event)
    - Event type
    - Result (pass/fail/retry/dead-letter or free-form)
    - Reason (if failure)
    """

    timestamp: str
    cycle_id: str
    category: EventCategory
    component: str
    event_type: str
    result: str = "ok"
    reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class AuditLogger:
    """In-memory append-only event log.

    Suitable for MVP. Phase 4 will provide a persistent backend that
    implements the same interface.
    """

    def __init__(self) -> None:
        self._records: list[AuditRecord] = []

    def record(
        self,
        cycle_id: str,
        category: EventCategory,
        component: str,
        event_type: str,
        result: str = "ok",
        reason: str | None = None,
        metadata: dict[str, Any] | None = None,
        timestamp: str | None = None,
    ) -> AuditRecord:
        """Append a record. Returns the record for inspection.

        The log is append-only: records cannot be modified or deleted.
        """
        record = AuditRecord(
            timestamp=timestamp or datetime.now(UTC).isoformat(),
            cycle_id=cycle_id,
            category=category,
            component=component,
            event_type=event_type,
            result=result,
            reason=reason,
            metadata=metadata or {},
        )
        self._records.append(record)
        return record

    def query(
        self,
        cycle_id: str | None = None,
        category: EventCategory | None = None,
        component: str | None = None,
        event_type: str | None = None,
    ) -> list[AuditRecord]:
        """Return records matching the given filters.

        All filters are optional; passing no filter returns all records.
        """
        results = list(self._records)
        if cycle_id is not None:
            results = [r for r in results if r.cycle_id == cycle_id]
        if category is not None:
            results = [r for r in results if r.category == category]
        if component is not None:
            results = [r for r in results if r.component == component]
        if event_type is not None:
            results = [r for r in results if r.event_type == event_type]
        return results

    def all_records(self) -> Iterable[AuditRecord]:
        """Return all records (read-only view)."""
        return tuple(self._records)

    def __len__(self) -> int:
        return len(self._records)

    def __bool__(self) -> bool:
        return bool(self._records)
