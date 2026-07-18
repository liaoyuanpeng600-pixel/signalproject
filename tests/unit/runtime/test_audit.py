"""Tests for the AuditLogger."""

from datetime import UTC, datetime

import pytest

from src.runtime.audit import AuditLogger, AuditRecord, EventCategory


class TestRecord:
    def test_record_returns_record(self) -> None:
        logger = AuditLogger()
        record = logger.record(
            cycle_id="cycle-1",
            category=EventCategory.CYCLE,
            component="executor",
            event_type="cycle_start",
        )
        assert isinstance(record, AuditRecord)
        assert record.cycle_id == "cycle-1"
        assert record.category == EventCategory.CYCLE
        assert record.component == "executor"
        assert record.event_type == "cycle_start"
        assert record.result == "ok"
        assert record.reason is None
        assert record.metadata == {}

    def test_record_with_all_fields(self) -> None:
        logger = AuditLogger()
        record = logger.record(
            cycle_id="cycle-1",
            category=EventCategory.FAILURE,
            component="harvester",
            event_type="source_unreachable",
            result="fail",
            reason="HTTP 503",
            metadata={"url": "https://example.com"},
        )
        assert record.result == "fail"
        assert record.reason == "HTTP 503"
        assert record.metadata == {"url": "https://example.com"}

    def test_record_with_explicit_timestamp(self) -> None:
        logger = AuditLogger()
        record = logger.record(
            cycle_id="cycle-1",
            category=EventCategory.CYCLE,
            component="executor",
            event_type="cycle_start",
            timestamp="2026-07-18T10:00:00+00:00",
        )
        assert record.timestamp == "2026-07-18T10:00:00+00:00"

    def test_record_auto_timestamp_is_iso8601_utc(self) -> None:
        logger = AuditLogger()
        before = datetime.now(UTC)
        record = logger.record(
            cycle_id="cycle-1",
            category=EventCategory.CYCLE,
            component="executor",
            event_type="cycle_start",
        )
        after = datetime.now(UTC)
        # Verify the timestamp is between before and after
        ts = datetime.fromisoformat(record.timestamp)
        assert before <= ts <= after


class TestQuery:
    def test_empty_logger_returns_empty(self) -> None:
        logger = AuditLogger()
        assert logger.query() == []
        assert len(logger) == 0
        assert not logger

    def test_query_by_cycle_id(self) -> None:
        logger = AuditLogger()
        logger.record("cycle-1", EventCategory.CYCLE, "c", "e1")
        logger.record("cycle-2", EventCategory.CYCLE, "c", "e2")
        logger.record("cycle-1", EventCategory.CYCLE, "c", "e3")
        result = logger.query(cycle_id="cycle-1")
        assert len(result) == 2
        assert all(r.cycle_id == "cycle-1" for r in result)

    def test_query_by_category(self) -> None:
        logger = AuditLogger()
        logger.record("c1", EventCategory.CYCLE, "c", "e1")
        logger.record("c1", EventCategory.GATE, "c", "e2")
        logger.record("c1", EventCategory.FAILURE, "c", "e3")
        result = logger.query(category=EventCategory.GATE)
        assert len(result) == 1
        assert result[0].event_type == "e2"

    def test_query_by_component(self) -> None:
        logger = AuditLogger()
        logger.record("c1", EventCategory.CYCLE, "executor", "e1")
        logger.record("c1", EventCategory.CYCLE, "validator", "e2")
        result = logger.query(component="executor")
        assert len(result) == 1
        assert result[0].event_type == "e1"

    def test_query_combined_filters(self) -> None:
        logger = AuditLogger()
        logger.record("cycle-1", EventCategory.GATE, "executor", "e1")
        logger.record("cycle-1", EventCategory.GATE, "validator", "e2")
        logger.record("cycle-2", EventCategory.GATE, "executor", "e3")
        result = logger.query(
            cycle_id="cycle-1", category=EventCategory.GATE, component="executor"
        )
        assert len(result) == 1
        assert result[0].event_type == "e1"


class TestAppendOnly:
    def test_records_are_frozen(self) -> None:
        logger = AuditLogger()
        record = logger.record("c", EventCategory.CYCLE, "c", "e")
        with pytest.raises(Exception):  # FrozenInstanceError
            record.event_type = "modified"  # type: ignore[misc]

    def test_records_cannot_be_deleted(self) -> None:
        logger = AuditLogger()
        logger.record("c", EventCategory.CYCLE, "c", "e1")
        logger.record("c", EventCategory.CYCLE, "c", "e2")
        # There is no delete method — log is append-only by design
        assert len(logger) == 2
        # No .delete() or .clear() or .remove() methods exist on AuditLogger
        assert not hasattr(logger, "delete")
        assert not hasattr(logger, "clear")
        assert not hasattr(logger, "remove")


class TestAllRecords:
    def test_returns_immutable_view(self) -> None:
        logger = AuditLogger()
        logger.record("c", EventCategory.CYCLE, "c", "e1")
        records = logger.all_records()
        assert len(records) == 1
        # tuple, not list — immutable view
        assert isinstance(records, tuple)
