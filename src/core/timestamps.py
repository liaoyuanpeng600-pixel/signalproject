"""
Timestamp utilities for SIGNAL objects.

All timestamps are ISO8601 UTC strings per Object Model and INV-10.

Example: "2026-07-18T12:34:56.789012+00:00"
"""

from __future__ import annotations

from datetime import datetime, timezone


def now_utc() -> str:
    """Return the current UTC time as an ISO8601 string.

    Returns:
        ISO8601 UTC timestamp string with microsecond precision.
    """
    return datetime.now(timezone.utc).isoformat()


def utc_from_timestamp(timestamp: datetime) -> str:
    """Convert a datetime to ISO8601 UTC string.

    If the datetime is naive, it is assumed to be UTC. If it has a timezone,
    it is converted to UTC.
    """
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc).isoformat()


def parse_iso8601_utc(value: str) -> datetime:
    """Parse an ISO8601 string and return a timezone-aware UTC datetime.

    Raises:
        ValueError: If the string is not a valid ISO8601 timestamp.
    """
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as e:
        raise ValueError(f"Invalid ISO8601 timestamp: {value!r}") from e

    if parsed.tzinfo is None:
        # Naive timestamps are rejected per INV-10.
        raise ValueError(
            f"Timestamp must be timezone-aware (UTC): {value!r}"
        )

    return parsed.astimezone(timezone.utc)


def is_valid_iso8601_utc(value: str) -> bool:
    """Check whether a string is a valid ISO8601 UTC timestamp."""
    try:
        parse_iso8601_utc(value)
        return True
    except ValueError:
        return False
