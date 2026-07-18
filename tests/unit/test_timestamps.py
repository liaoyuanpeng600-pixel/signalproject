"""Tests for the timestamps module (INV-10)."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from src.core.timestamps import (
    is_valid_iso8601_utc,
    now_utc,
    parse_iso8601_utc,
    utc_from_timestamp,
)


class TestNowUTC:
    def test_returns_iso8601_string(self) -> None:
        ts = now_utc()
        assert isinstance(ts, str)
        assert is_valid_iso8601_utc(ts)

    def test_close_to_current_time(self) -> None:
        before = datetime.now(UTC)
        ts = now_utc()
        after = datetime.now(UTC)
        parsed = parse_iso8601_utc(ts)
        assert before - timedelta(seconds=1) <= parsed <= after + timedelta(seconds=1)


class TestParseISO8601UTC:
    def test_parses_utc_string(self) -> None:
        ts = "2026-07-18T12:34:56.789012+00:00"
        parsed = parse_iso8601_utc(ts)
        assert parsed.year == 2026
        assert parsed.month == 7
        assert parsed.day == 18
        assert parsed.hour == 12
        assert parsed.tzinfo is not None

    def test_converts_other_timezones_to_utc(self) -> None:
        # Same instant expressed in different timezones should equal the same UTC.
        ts_utc = "2026-07-18T12:00:00+00:00"
        ts_est = "2026-07-18T08:00:00-04:00"  # Same instant
        assert parse_iso8601_utc(ts_utc) == parse_iso8601_utc(ts_est)

    def test_rejects_invalid_format(self) -> None:
        with pytest.raises(ValueError):
            parse_iso8601_utc("not-a-timestamp")

    def test_rejects_naive_timestamp(self) -> None:
        # No timezone info
        with pytest.raises(ValueError):
            parse_iso8601_utc("2026-07-18T12:00:00")


class TestUtcFromTimestamp:
    def test_naive_datetime_assumed_utc(self) -> None:
        naive = datetime(2026, 7, 18, 12, 0, 0)
        ts = utc_from_timestamp(naive)
        assert is_valid_iso8601_utc(ts)
        parsed = parse_iso8601_utc(ts)
        assert parsed.hour == 12

    def test_aware_datetime_converted(self) -> None:
        # Datetime in a non-UTC timezone
        tz = timezone(timedelta(hours=-4))  # EDT-ish
        aware = datetime(2026, 7, 18, 8, 0, 0, tzinfo=tz)
        ts = utc_from_timestamp(aware)
        parsed = parse_iso8601_utc(ts)
        assert parsed.hour == 12  # Converted to UTC
        assert parsed.utcoffset() == timedelta(0)


class TestIsValidISO8601UTC:
    def test_valid_utc(self) -> None:
        assert is_valid_iso8601_utc("2026-07-18T12:00:00+00:00")
        assert is_valid_iso8601_utc("2026-07-18T12:00:00.123456Z")
        assert is_valid_iso8601_utc("2026-07-18T12:00:00-04:00")

    def test_invalid(self) -> None:
        assert not is_valid_iso8601_utc("not-a-timestamp")
        assert not is_valid_iso8601_utc("")
        assert not is_valid_iso8601_utc("2026-13-01T00:00:00")  # Invalid month
