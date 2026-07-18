"""Tests for the IDs module."""

import re

from src.core.ids import ID, is_valid_id, new_id


class TestNewID:
    def test_returns_string(self) -> None:
        result = new_id()
        assert isinstance(result, str)

    def test_returns_unique_ids(self) -> None:
        ids = {new_id() for _ in range(100)}
        assert len(ids) == 100

    def test_returns_uuid4_format(self) -> None:
        result = new_id()
        # UUIDv4 format: 8-4-4-4-12 hex chars
        assert re.match(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
            result,
        ), f"Not a UUIDv4: {result}"


class TestIsValidID:
    def test_non_empty_string_is_valid(self) -> None:
        assert is_valid_id("any-string")

    def test_empty_string_is_invalid(self) -> None:
        assert not is_valid_id("")

    def test_non_string_is_invalid(self) -> None:
        assert not is_valid_id(123)  # type: ignore[arg-type]
        assert not is_valid_id(None)  # type: ignore[arg-type]
