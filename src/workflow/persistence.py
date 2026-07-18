"""
Persistence interface for the workflow layer.

The workflow module does NOT persist directly. It uses a Persistence
interface so the storage backend (in-memory for MVP, database for production)
can be swapped without changing workflow logic.

Per the user constraint: "No direct persistence logic inside the workflow
layer."

Per Workflow Model §"Persistence": "Stores Objects per Object Model
lifecycle rules."

The interface defined here is a CONTRACT. Phase 4 will provide concrete
implementations (InMemoryPersistence, DatabasePersistence).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable

from src.core.entities import Entity
from src.core.evidence import Evidence
from src.core.ids import ID
from src.core.research import Research
from src.core.signals import Signal
from src.core.sources import Source
from src.core.theses import Thesis


class Persistence(ABC):
    """Abstract interface for Object persistence."""

    # ---- Write operations ----

    @abstractmethod
    def save_source(self, source: Source) -> None:
        """Persist a Source (immutable on creation, mutable on transition)."""

    @abstractmethod
    def save_entity(self, entity: Entity) -> None:
        """Persist an Entity."""

    @abstractmethod
    def save_evidence(self, evidence: Evidence) -> None:
        """Persist an Evidence (immutable)."""

    @abstractmethod
    def save_signal(self, signal: Signal) -> None:
        """Persist a Signal."""

    @abstractmethod
    def save_research(self, research: Research) -> None:
        """Persist a Research."""

    @abstractmethod
    def save_thesis(self, thesis: Thesis) -> None:
        """Persist a Thesis."""

    @abstractmethod
    def save_override_record(self, override_record: object) -> None:
        """Append an OverrideRecord (append-only per INV-11)."""

    # ---- Read operations ----

    @abstractmethod
    def get_source(self, source_id: ID) -> Source | None:
        """Retrieve a Source by ID."""

    @abstractmethod
    def get_entity(self, entity_id: ID) -> Entity | None:
        """Retrieve an Entity by ID."""

    @abstractmethod
    def get_evidence(self, evidence_id: ID) -> Evidence | None:
        """Retrieve an Evidence by ID (immutable)."""

    @abstractmethod
    def get_signal(self, signal_id: ID) -> Signal | None:
        """Retrieve a Signal by ID."""

    @abstractmethod
    def get_research(self, research_id: ID) -> Research | None:
        """Retrieve a Research by ID."""

    @abstractmethod
    def get_thesis(self, thesis_id: ID) -> Thesis | None:
        """Retrieve a Thesis by ID."""

    @abstractmethod
    def get_all_active_signals(self) -> Iterable[Signal]:
        """Retrieve all currently-active signals."""

    @abstractmethod
    def get_research_for_entity(self, entity_id: ID) -> Iterable[Research]:
        """Retrieve all Research for a given Entity."""

    @abstractmethod
    def get_thesis_for_entity(self, entity_id: ID) -> Thesis | None:
        """Retrieve the current Thesis for a given Entity (if any)."""

    # ---- Checkpoint operations ----

    @abstractmethod
    def checkpoint(self, cycle_id: ID) -> None:
        """Create a checkpoint of the current state for a cycle."""

    @abstractmethod
    def restore(self, cycle_id: ID) -> bool:
        """Restore from a checkpoint. Returns True if successful."""


class InMemoryPersistence(Persistence):
    """In-memory persistence implementation.

    Suitable for MVP and testing. Phase 4 will replace this with a
    production persistence backend.
    """

    def __init__(self) -> None:
        self._sources: dict[ID, Source] = {}
        self._entities: dict[ID, Entity] = {}
        self._evidences: dict[ID, Evidence] = {}
        self._signals: dict[ID, Signal] = {}
        self._research: dict[ID, Research] = {}
        self._theses: dict[ID, Thesis] = {}
        self._override_records: list[object] = []
        self._checkpoints: dict[ID, dict[str, dict[ID, object]]] = {}

    # ---- Write ----

    def save_source(self, source: Source) -> None:
        self._sources[source.id] = source

    def save_entity(self, entity: Entity) -> None:
        self._entities[entity.id] = entity

    def save_evidence(self, evidence: Evidence) -> None:
        # Evidence is immutable — overwriting is permitted because the ID
        # is the same (immutability = no in-place mutation, but persistence
        # can update the record).
        self._evidences[evidence.id] = evidence

    def save_signal(self, signal: Signal) -> None:
        self._signals[signal.id] = signal

    def save_research(self, research: Research) -> None:
        self._research[research.id] = research

    def save_thesis(self, thesis: Thesis) -> None:
        # Thesis is replaced (frozen dataclass); new instance replaces old.
        self._theses[thesis.id] = thesis

    def save_override_record(self, override_record: object) -> None:
        # INV-11: append-only.
        self._override_records.append(override_record)

    # ---- Read ----

    def get_source(self, source_id: ID) -> Source | None:
        return self._sources.get(source_id)

    def get_entity(self, entity_id: ID) -> Entity | None:
        return self._entities.get(entity_id)

    def get_evidence(self, evidence_id: ID) -> Evidence | None:
        return self._evidences.get(evidence_id)

    def get_signal(self, signal_id: ID) -> Signal | None:
        return self._signals.get(signal_id)

    def get_research(self, research_id: ID) -> Research | None:
        return self._research.get(research_id)

    def get_thesis(self, thesis_id: ID) -> Thesis | None:
        return self._theses.get(thesis_id)

    def get_all_active_signals(self) -> Iterable[Signal]:
        from src.core.signals import SignalStatus

        return (s for s in self._signals.values() if s.status == SignalStatus.ACTIVE)

    def get_research_for_entity(self, entity_id: ID) -> Iterable[Research]:
        return (r for r in self._research.values() if r.entity_ref.id == entity_id)

    def get_thesis_for_entity(self, entity_id: ID) -> Thesis | None:
        # Return the most recent (highest evolution_history length) thesis for the entity.
        candidates = [t for t in self._theses.values() if t.entity_ref.id == entity_id]
        if not candidates:
            return None
        return max(candidates, key=lambda t: len(t.evolution_history))

    # ---- Checkpoint ----

    def checkpoint(self, cycle_id: ID) -> None:
        self._checkpoints[cycle_id] = {
            "sources": dict(self._sources),
            "entities": dict(self._entities),
            "evidences": dict(self._evidences),
            "signals": dict(self._signals),
            "research": dict(self._research),
            "theses": dict(self._theses),
        }

    def restore(self, cycle_id: ID) -> bool:
        snapshot = self._checkpoints.get(cycle_id)
        if snapshot is None:
            return False
        self._sources = dict(snapshot["sources"])  # type: ignore[assignment]
        self._entities = dict(snapshot["entities"])  # type: ignore[assignment]
        self._evidences = dict(snapshot["evidences"])  # type: ignore[assignment]
        self._signals = dict(snapshot["signals"])  # type: ignore[assignment]
        self._research = dict(snapshot["research"])  # type: ignore[assignment]
        self._theses = dict(snapshot["theses"])  # type: ignore[assignment]
        return True