"""
Knowledge type per Object Model §7.

Knowledge is the accumulated, interconnected body of Theses, Research, Signals,
and Evidence that the system retains over time. Knowledge is not a single
object; it is the accumulated corpus.

In Phase 1, we provide the KnowledgeAccumulator interface and a basic
in-memory implementation. Persistence backends come in Phase 4.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable

from src.core.entities import Entity
from src.core.evidence import Evidence
from src.core.ids import ID
from src.core.research import Research
from src.core.signals import Signal, SignalStatus
from src.core.theses import Thesis


class KnowledgeAccumulator(ABC):
    """Abstract interface for Knowledge accumulation.

    Implementations:
    - InMemoryKnowledge (Phase 1 / MVP)
    - PersistentKnowledge (Phase 4, with backend)
    """

    @abstractmethod
    def add_thesis(self, thesis: Thesis) -> None:
        """Integrate a Thesis into Knowledge."""

    @abstractmethod
    def add_research(self, research: Research) -> None:
        """Add Research to Knowledge."""

    @abstractmethod
    def add_signal(self, signal: Signal) -> None:
        """Add a Signal to Knowledge. Only ACTIVE signals are typically included."""

    @abstractmethod
    def add_evidence(self, evidence: Evidence) -> None:
        """Add Evidence to Knowledge. Evidence is immutable; this records it."""

    @abstractmethod
    def get_theses_for_entity(self, entity_id: ID) -> tuple[Thesis, ...]:
        """Return all Theses for a given Entity."""

    @abstractmethod
    def get_active_signals_for_entity(self, entity_id: ID) -> tuple[Signal, ...]:
        """Return all ACTIVE signals for a given Entity."""

    @abstractmethod
    def get_research_for_entity(self, entity_id: ID) -> tuple[Research, ...]:
        """Return all Research for a given Entity."""

    @abstractmethod
    def get_evidence_for_signal(self, signal_id: ID) -> tuple[Evidence, ...]:
        """Return all Evidence grounding a given Signal."""

    @abstractmethod
    def get_all_entities(self) -> Iterable[Entity]:
        """Return all known Entities."""


class InMemoryKnowledge(KnowledgeAccumulator):
    """In-memory implementation of Knowledge accumulation.

    Suitable for MVP and testing. Phase 4 will add a persistent backend.
    """

    def __init__(self) -> None:
        # Indexed by id for fast lookup; secondary indexes by entity_ref.
        self._theses: dict[ID, Thesis] = {}
        self._research: dict[ID, Research] = {}
        self._signals: dict[ID, Signal] = {}
        self._evidence: dict[ID, Evidence] = {}
        self._entities: dict[ID, Entity] = {}

        # Secondary indexes: entity_id -> list of object ids.
        self._theses_by_entity: dict[ID, list[ID]] = {}
        self._research_by_entity: dict[ID, list[ID]] = {}
        self._signals_by_entity: dict[ID, list[ID]] = {}
        self._evidence_by_signal: dict[ID, list[ID]] = {}

    def add_thesis(self, thesis: Thesis) -> None:
        self._theses[thesis.id] = thesis
        self._theses_by_entity.setdefault(thesis.entity_ref.id, []).append(thesis.id)

    def add_research(self, research: Research) -> None:
        self._research[research.id] = research
        self._research_by_entity.setdefault(research.entity_ref.id, []).append(research.id)

    def add_signal(self, signal: Signal) -> None:
        self._signals[signal.id] = signal
        self._signals_by_entity.setdefault(signal.entity_ref.id, []).append(signal.id)

    def add_evidence(self, evidence: Evidence) -> None:
        self._evidence[evidence.id] = evidence
        for signal_id in evidence.source_ids:
            # Evidence's source_ids reference Sources, not Signals.
            # For "evidence grounding signal" lookups, see get_evidence_for_signal.
            pass

    def link_evidence_to_signal(self, signal_id: ID, evidence_id: ID) -> None:
        """Record that an Evidence grounds a Signal.

        This is the proper Signal-to-Evidence link (vs. Evidence.source_ids
        which are Evidence-to-Source links).
        """
        self._evidence_by_signal.setdefault(signal_id, []).append(evidence_id)

    def get_theses_for_entity(self, entity_id: ID) -> tuple[Thesis, ...]:
        ids = self._theses_by_entity.get(entity_id, [])
        return tuple(self._theses[tid] for tid in ids if tid in self._theses)

    def get_active_signals_for_entity(self, entity_id: ID) -> tuple[Signal, ...]:
        ids = self._signals_by_entity.get(entity_id, [])
        active = (
            self._signals[sid]
            for sid in ids
            if sid in self._signals and self._signals[sid].status == SignalStatus.ACTIVE
        )
        return tuple(active)

    def get_research_for_entity(self, entity_id: ID) -> tuple[Research, ...]:
        ids = self._research_by_entity.get(entity_id, [])
        return tuple(self._research[rid] for rid in ids if rid in self._research)

    def get_evidence_for_signal(self, signal_id: ID) -> tuple[Evidence, ...]:
        ids = self._evidence_by_signal.get(signal_id, [])
        return tuple(self._evidence[eid] for eid in ids if eid in self._evidence)

    def get_all_entities(self) -> Iterable[Entity]:
        return self._entities.values()

    def add_entity(self, entity: Entity) -> None:
        """Track an Entity. (Helper beyond the abstract interface.)"""
        self._entities[entity.id] = entity

    # ---- Stats (useful for tests and runtime observability) ----

    def thesis_count(self) -> int:
        return len(self._theses)

    def signal_count(self, status: SignalStatus | None = None) -> int:
        if status is None:
            return len(self._signals)
        return sum(1 for s in self._signals.values() if s.status == status)

    def evidence_count(self) -> int:
        return len(self._evidence)
