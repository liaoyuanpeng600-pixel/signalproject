"""
Thesis type per Object Model §6.

A Thesis is a living research object that articulates a coherent
interpretation about an Entity, sector, or question. Thesis is the central
organizing unit of research understanding.

Thesis evolves continuously; every state transition is recorded in the
evolution_history.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum

from src.core.ids import ID, new_id
from src.core.lifecycle import THESIS_LIFECYCLE, ThesisStatus, assert_transition
from src.core.signals import EntityRef
from src.core.timestamps import now_utc


@dataclass(frozen=True, slots=True)
class ThesisEvolution:
    """A single evolution event in a Thesis's history.

    Every time a Thesis's interpretation changes, a new ThesisEvolution is
    appended. The Thesis itself is replaced (frozen dataclass), so history is
    preserved by the tuple of evolutions.
    """

    at: str  # ISO8601 UTC timestamp
    by: str  # What triggered the evolution: research_id, curator, etc.
    kind: str  # "evolve" | "supersede" | "open_question"
    prior_interpretation: str
    new_interpretation: str
    contributing_research_ids: tuple[ID, ...] = ()
    rationale: str = ""

    def __post_init__(self) -> None:
        if not self.at:
            raise ValueError("ThesisEvolution.at is required")
        if not self.by:
            raise ValueError("ThesisEvolution.by is required")
        if self.kind not in {"evolve", "supersede", "open_question"}:
            raise ValueError(f"ThesisEvolution.kind must be one of evolve/supersede/open_question, got {self.kind!r}")


@dataclass(frozen=True, slots=True)
class Thesis:
    """A living research object (central organizing unit).

    Thesis is frozen: id is immutable. Evolution is captured by replacing the
    Thesis with a new instance that has an additional ThesisEvolution in its
    history tuple.
    """

    id: ID
    entity_ref: EntityRef
    interpretation: str  # The coherent interpretation
    status: ThesisStatus = ThesisStatus.EMERGING
    supporting_research_ids: tuple[ID, ...] = ()
    evolution_history: tuple[ThesisEvolution, ...] = ()
    created_at: str = field(default_factory=now_utc)
    open_questions: tuple[str, ...] = ()  # Annotations for Path C (Hold)

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("Thesis.id is required")
        if not self.interpretation:
            raise ValueError("Thesis.interpretation is required")
        if len(self.interpretation) > 2000:
            # Soft cap; reports will further constrain
            raise ValueError(f"Thesis.interpretation too long: {len(self.interpretation)} chars")

    def transition(self, new_status: ThesisStatus) -> "Thesis":
        """Transition to a new status. Validates against THESIS_LIFECYCLE.

        Raises:
            LifecycleError: If the transition is not allowed.
        """
        assert_transition(THESIS_LIFECYCLE, self.status, new_status)
        return replace(self, status=new_status)

    def evolve(
        self,
        new_interpretation: str,
        contributing_research_ids: tuple[ID, ...],
        by: str,
        rationale: str = "",
    ) -> "Thesis":
        """Evolve the Thesis with a new interpretation.

        Appends a ThesisEvolution to the history. Path A (Evolve) per
        Workflow Model Rule 2. Transitions EMERGING -> EVOLVING, leaves
        EVOLVING as EVOLVING, and reopens MATURE -> EVOLVING.
        """
        if not new_interpretation:
            raise ValueError("Thesis.interpretation cannot be empty")
        evolution = ThesisEvolution(
            at=now_utc(),
            by=by,
            kind="evolve",
            prior_interpretation=self.interpretation,
            new_interpretation=new_interpretation,
            contributing_research_ids=contributing_research_ids,
            rationale=rationale,
        )
        new_history = self.evolution_history + (evolution,)
        # EMERGING -> EVOLVING on first evolution; MATURE -> EVOLVING on reopen;
        # EVOLVING stays EVOLVING.
        if self.status in (ThesisStatus.EMERGING, ThesisStatus.MATURE):
            new_status = ThesisStatus.EVOLVING
        else:
            new_status = self.status  # EVOLVING or SUPERSEDED/RETIRED (terminal)
        return replace(
            self,
            interpretation=new_interpretation,
            status=new_status,
            evolution_history=new_history,
        )

    def mature(self) -> "Thesis":
        """Mark the Thesis as mature (Path A completion)."""
        return self.transition(ThesisStatus.MATURE)

    def supersede_with(
        self,
        new_interpretation: str,
        by: str,
        prior_id: ID,
    ) -> "Thesis":
        """Create a new Thesis that supersedes this one. Path B per Workflow Model.

        The new Thesis records that it superseded prior_id; this Thesis (the
        prior) is marked superseded. The caller is responsible for marking
        this Thesis as superseded (via self.supersede()).
        """
        if not new_interpretation:
            raise ValueError("New Thesis.interpretation cannot be empty")
        evolution = ThesisEvolution(
            at=now_utc(),
            by=by,
            kind="supersede",
            prior_interpretation=self.interpretation,
            new_interpretation=new_interpretation,
            contributing_research_ids=(),
            rationale=f"Supersedes Thesis {prior_id}",
        )
        new_history = self.evolution_history + (evolution,)
        return Thesis(
            id=new_id(),
            entity_ref=self.entity_ref,
            interpretation=new_interpretation,
            status=ThesisStatus.EMERGING,
            evolution_history=new_history,
        )

    def supersede(self, by: str = "supersede_event") -> "Thesis":
        """Mark this Thesis as superseded (terminal)."""
        if self.status == ThesisStatus.SUPERSEDED:
            return self
        evolution = ThesisEvolution(
            at=now_utc(),
            by=by,
            kind="supersede",
            prior_interpretation=self.interpretation,
            new_interpretation="(superseded)",
            contributing_research_ids=(),
        )
        new_history = self.evolution_history + (evolution,)
        new = self.transition(ThesisStatus.SUPERSEDED)
        return replace(new, evolution_history=new_history)

    def retire(self, by: str = "retire_event") -> "Thesis":
        """Mark this Thesis as retired (terminal)."""
        if self.status == ThesisStatus.RETIRED:
            return self
        return self.transition(ThesisStatus.RETIRED)

    def hold_with_open_question(self, question: str) -> "Thesis":
        """Annotate the Thesis with an open question (Path C / Hold)."""
        return replace(self, open_questions=self.open_questions + (question,))

    def add_supporting_research(self, research_id: ID) -> "Thesis":
        """Append a supporting Research ID."""
        if research_id in self.supporting_research_ids:
            return self
        return replace(
            self,
            supporting_research_ids=self.supporting_research_ids + (research_id,),
        )

    @classmethod
    def create(
        cls,
        entity_ref: EntityRef,
        interpretation: str,
        id: ID | None = None,
        supporting_research_ids: tuple[ID, ...] = (),
        status: ThesisStatus = ThesisStatus.EMERGING,
    ) -> "Thesis":
        """Factory method to create a new Thesis."""
        return cls(
            id=id if id is not None else new_id(),
            entity_ref=entity_ref,
            interpretation=interpretation,
            status=status,
            supporting_research_ids=supporting_research_ids,
        )
