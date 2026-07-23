"""
SIGNAL Persistence — Phase 4.

This package implements Object persistence per the Object Model lifecycle rules.
MVP scope: in-memory backend only (production database is post-MVP).

Modules:
- store: Abstract `Store` Protocol defining the persistence contract.
- in_memory: `InMemoryStore` — the MVP backend.
- lifecycle: Helpers for lifecycle transitions (retire, supersede).
- checkpoint: Snapshot + restore of store contents.
- override: `OverrideRecord` (append-only, INV-11).

Enforces:
- Evidence immutability (write-once semantics; overwrite rejected).
- OverrideRecord append-only (INV-11).
- Object identity preservation (ID-based addressing).
- Lifecycle transitions via central helpers.

See docs/01_OBJECT_MODEL.md for canonical semantics and
docs/IMPLEMENTATION_ROADMAP.md §"Phase 4" for scope.
"""

from __future__ import annotations

from src.persistence.in_memory import InMemoryStore
from src.persistence.override import OverrideAction, OverrideRecord
from src.persistence.store import Store

__all__ = [
    "InMemoryStore",
    "OverrideAction",
    "OverrideRecord",
    "Store",
]