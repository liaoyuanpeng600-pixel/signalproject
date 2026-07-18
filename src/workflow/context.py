"""
PipelineContext — mutable state holder for a single workflow cycle.

The context carries in-flight Objects as they move through stages. It does
NOT persist anything; that is Persistence's job (Phase 4).

The context also accumulates events as the cycle progresses.

Per Workflow Model §"Object Transition Table":
- Stage 1: produces Candidate observations
- Stage 2: produces Evidence
- Stage 3: produces Signals (verified) or rejects signal drafts
- Stage 4: produces Research
- Stage 5: produces Theses
- Stage 6: integrates Theses into Knowledge
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.core.entities import Entity
from src.core.evidence import Evidence
from src.core.ids import ID, new_id
from src.core.research import Research
from src.core.signals import Signal
from src.core.sources import Source
from src.core.theses import Thesis
from src.core.timestamps import now_utc
from src.workflow.events import WorkflowEvent
from src.workflow.types import CandidateObservation


@dataclass
class PipelineContext:
    """State for a single workflow cycle.

    The context is mutable; stages add to its containers as they process.
    Failure-path destinations are separate containers that accumulate
    rejected / held / pending objects.
    """

    cycle_id: ID = field(default_factory=new_id)
    started_at: str = field(default_factory=now_utc)

    # Inputs (loaded at cycle start)
    sources: list[Source] = field(default_factory=list)
    entities: list[Entity] = field(default_factory=list)

    # Stage 1 outputs
    candidates: list[CandidateObservation] = field(default_factory=list)
    flagged_candidates: list[CandidateObservation] = field(default_factory=list)  # S1-G3 fail
    degraded_sources: list[Source] = field(default_factory=list)  # S1-G1/G2 fail

    # Stage 2 outputs
    evidences: list[Evidence] = field(default_factory=list)
    rejected_evidences: list[Evidence] = field(default_factory=list)
    non_retrievable_evidences: list[Evidence] = field(default_factory=list)

    # Stage 3 outputs
    signals: list[Signal] = field(default_factory=list)  # verified signals
    rejected_signal_drafts: list[Signal] = field(default_factory=list)  # failed gates

    # Stage 4 outputs
    research_list: list[Research] = field(default_factory=list)
    held_research: list[Research] = field(default_factory=list)
    research_with_traceability_gaps: list[Research] = field(default_factory=list)

    # Stage 5 outputs
    theses: list[Thesis] = field(default_factory=list)
    held_theses: list[Thesis] = field(default_factory=list)

    # Stage 6 outputs
    theses_pending: list[Thesis] = field(default_factory=list)

    # Audit trail (consumers subscribe via events)
    events: list[WorkflowEvent] = field(default_factory=list)

    def emit(self, event: WorkflowEvent) -> None:
        """Append an event to the audit trail."""
        self.events.append(event)

    # ---- Stage transition statistics (for CycleReport) ----

    @property
    def signals_emitted(self) -> int:
        """Number of signals that completed Stage 3 successfully."""
        return len(self.signals)

    @property
    def research_emitted(self) -> int:
        """Number of research objects produced."""
        return len(self.research_list)

    @property
    def theses_updated(self) -> int:
        """Number of theses that completed Stage 5."""
        return len(self.theses)

    @property
    def evidences_produced(self) -> int:
        """Number of evidences produced (including non-retrievable)."""
        return len(self.evidences) + len(self.non_retrievable_evidences)