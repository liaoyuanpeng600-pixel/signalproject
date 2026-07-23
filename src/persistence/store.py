"""
Persistence Store interface.

`Store` is the contract that all persistence backends implement. Runtime and
workflow modules depend on this interface only — never on a concrete backend.

Invariants enforced regardless of backend:
- Evidence immutability: once stored, Evidence cannot be overwritten.
- OverrideRecord append-only: new records are appended, never modified.
- Object identity: addressed by ID; the same ID always returns the same Object
  (modulo supersession, which produces a new Object).
- Lifecycle transitions: callers should use lifecycle helpers, not direct
  status mutation, but the store does not enforce state graph validity (that
  is the lifecycle module's responsibility).

See docs/IMPLEMENTATION_ROADMAP.md §"Phase 4" for scope.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.entities import Entity
    from src.core.evidence import Evidence
    from src.core.research import Research
    from src.core.signals import Signal
    from src.core.sources import Source
    from src.core.theses import Thesis

    from src.persistence.override import OverrideRecord


class Store(ABC):
    """Abstract persistence backend.

    The MVP ships `InMemoryStore`. Production backends (PostgreSQL, etc.) come
    post-MVP and must conform to this interface.
    """

    # ---- Entities ----

    @abstractmethod
    def put_entity(self, entity: "Entity") -> None:
        """Persist an Entity. Replaces any existing Entity with the same ID."""

    @abstractmethod
    def get_entity(self, entity_id: str) -> "Entity | None":
        """Retrieve an Entity by ID, or None if not stored."""

    @abstractmethod
    def list_entities(self) -> tuple["Entity", ...]:
        """Return all stored Entities."""

    # ---- Sources ----

    @abstractmethod
    def put_source(self, source: "Source") -> None:
        """Persist a Source. Replaces any existing Source with the same ID."""

    @abstractmethod
    def get_source(self, source_id: str) -> "Source | None":
        """Retrieve a Source by ID."""

    @abstractmethod
    def list_sources(self) -> tuple["Source", ...]:
        """Return all stored Sources."""

    # ---- Evidence (immutable) ----

    @abstractmethod
    def put_evidence(self, evidence: "Evidence") -> None:
        """Persist Evidence. Raises EvidenceAlreadyExists on overwrite attempt."""

    @abstractmethod
    def get_evidence(self, evidence_id: str) -> "Evidence | None":
        """Retrieve Evidence by ID."""

    @abstractmethod
    def list_evidence(self) -> tuple["Evidence", ...]:
        """Return all stored Evidence."""

    # ---- Signals ----

    @abstractmethod
    def put_signal(self, signal: "Signal") -> None:
        """Persist a Signal. Replaces any existing Signal with the same ID."""

    @abstractmethod
    def get_signal(self, signal_id: str) -> "Signal | None":
        """Retrieve a Signal by ID."""

    @abstractmethod
    def list_signals(self) -> tuple["Signal", ...]:
        """Return all stored Signals."""

    # ---- Research ----

    @abstractmethod
    def put_research(self, research: "Research") -> None:
        """Persist Research. Replaces any existing Research with the same ID."""

    @abstractmethod
    def get_research(self, research_id: str) -> "Research | None":
        """Retrieve Research by ID."""

    @abstractmethod
    def list_research(self) -> tuple["Research", ...]:
        """Return all stored Research."""

    # ---- Theses ----

    @abstractmethod
    def put_thesis(self, thesis: "Thesis") -> None:
        """Persist a Thesis. Replaces any existing Thesis with the same ID."""

    @abstractmethod
    def get_thesis(self, thesis_id: str) -> "Thesis | None":
        """Retrieve a Thesis by ID."""

    @abstractmethod
    def list_theses(self) -> tuple["Thesis", ...]:
        """Return all stored Theses."""

    # ---- Override Records (append-only) ----

    @abstractmethod
    def append_override(self, record: "OverrideRecord") -> None:
        """Append an OverrideRecord. Existing records cannot be modified or
        removed; this always appends to the immutable log."""

    @abstractmethod
    def list_overrides(self, target_id: str | None = None) -> tuple["OverrideRecord", ...]:
        """Return OverrideRecords, optionally filtered by target Object ID.
        Returns ALL records if target_id is None."""

    # ---- Bulk operations ----

    @abstractmethod
    def clear(self) -> None:
        """Remove all stored objects. Used by tests and checkpoint restore."""

    @abstractmethod
    def snapshot(self) -> dict[str, object]:
        """Return a JSON-serializable snapshot of all stored objects."""

    @abstractmethod
    def restore(self, snapshot: dict[str, object]) -> None:
        """Replace store contents from a snapshot. Used by checkpoint restore."""