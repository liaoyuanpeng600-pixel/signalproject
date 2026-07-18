"""
ID generation for SIGNAL objects.

This module provides a single ID type and a generator. In Phase 1, IDs are
UUIDv4 strings. The Object Model specifies ULID format; ULIDs can be
introduced as a migration without changing the ID interface.

INVARIANT: IDs are immutable once assigned (INV-2).
"""

from __future__ import annotations

from typing import NewType
from uuid import uuid4

# Type alias for clarity. Use this in type annotations.
ID = NewType("ID", str)


def new_id() -> ID:
    """Generate a new ID.

    Returns a UUIDv4 string wrapped in the ID type. Stable, unique, and
    string-serializable.
    """
    return ID(str(uuid4()))


def is_valid_id(value: str) -> bool:
    """Check whether a value is a non-empty ID-shaped string.

    This is a permissive validator: any non-empty string is acceptable for
    Phase 1. Once ULID is introduced, this becomes strict (26 chars,
    Crockford base32).
    """
    return isinstance(value, str) and len(value) > 0
