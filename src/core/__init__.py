"""
SIGNAL Core — Phase 1.

This package contains the 7 Object types from the Object Model:
- Entity, Source, Evidence, Signal, Research, Thesis, Knowledge

Plus shared primitives: ids, timestamps, lifecycle, invariants.

See docs/01_OBJECT_MODEL.md for the canonical specification.
"""

from __future__ import annotations

# Re-export subpackages for convenient access.
from src.core import evidence, ids, invariants, knowledge, lifecycle, research, signals, sources, theses, timestamps, entities

__all__ = [
    "entities",
    "evidence",
    "ids",
    "invariants",
    "knowledge",
    "lifecycle",
    "research",
    "signals",
    "sources",
    "theses",
    "timestamps",
]
