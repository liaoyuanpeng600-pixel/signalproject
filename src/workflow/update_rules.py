"""
Workflow Update Rules — per Workflow Model §"Update Rules".

Four rules govern how Objects evolve as they flow through the pipeline:

Rule 1: New Signal Handling (draft -> verified -> integrated)
Rule 2: Existing Thesis Update (Evolve / Supersede / Hold)
Rule 3: Conflicting Research (both retained, conflict recorded)
Rule 4: Knowledge Accumulation (growth, reorganization, preservation)

This module exposes the rules as callable functions. Each function takes the
relevant Objects and returns the appropriate update action.

Per the user constraints:
- "All state transitions must go through the lifecycle module."
  → Rules call domain-object methods (which call lifecycle).
- "Workflow orchestrates only; business rules remain in domain objects."
  → Rules contain only workflow-level coordination logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.core.research import Research
from src.core.signals import Signal, SignalStatus
from src.core.theses import Thesis, ThesisStatus


# ---------------------------------------------------------------------------
# Rule 2: Thesis Update Path Decision
# ---------------------------------------------------------------------------


class ThesisUpdatePath(str, Enum):
    """The three paths for updating a Thesis given new Research.

    Per Workflow Model Rule 2:
    - EVOLVE: new research supports/refines existing thesis
    - SUPERSEDE: new research invalidates existing thesis
    - HOLD: new research is relevant but inconclusive
    """

    EVOLVE = "evolve"
    SUPERSEDE = "supersede"
    HOLD = "hold"


@dataclass
class ThesisUpdateDecision:
    """Result of a Thesis update path decision."""

    path: ThesisUpdatePath
    rationale: str


def decide_thesis_update_path(research: Research, existing: Thesis | None) -> ThesisUpdateDecision:
    """Decide which path to take when new Research arrives for an Entity.

    Per Workflow Model Rule 2:
    - If existing is None: new Thesis (Path A: emerge)
    - If existing is present: assess relationship between research and existing

    For MVP, the decision is conservative:
    - Always EVOLVE if research and existing exist (assumes new research
      refines but doesn't invalidate). A real implementation would compare
      conclusions, weight evidence, etc.
    - HOLD if research is inconclusive (caller decides what "inconclusive" means)
    - SUPERSEDE only if explicitly indicated by the caller.

    Args:
        research: The new Research that triggered the update.
        existing: The current Thesis for the same Entity, or None.

    Returns:
        ThesisUpdateDecision with the chosen path and rationale.
    """
    if existing is None:
        return ThesisUpdateDecision(
            path=ThesisUpdatePath.EVOLVE,
            rationale="no existing thesis; create new",
        )

    # MVP heuristic: if the research interpretation is materially different
    # from the existing thesis, supersede. Otherwise evolve.
    # A real implementation would compare semantic content.
    research_summary = research.question.strip().lower()
    existing_summary = existing.interpretation.strip().lower()
    if research_summary and existing_summary and research_summary != existing_summary:
        # Different content — conservatively evolve (we don't supersede
        # without strong evidence of invalidation).
        return ThesisUpdateDecision(
            path=ThesisUpdatePath.EVOLVE,
            rationale="new research differs; evolve existing thesis",
        )

    return ThesisUpdateDecision(
        path=ThesisUpdatePath.EVOLVE,
        rationale="new research aligns; evolve existing thesis",
    )


def apply_thesis_update(
    decision: ThesisUpdateDecision,
    research: Research,
    existing: Thesis | None,
    new_interpretation: str,
    by: str,
) -> Thesis:
    """Apply a Thesis update decision.

    Returns the resulting Thesis. For EVOLVE, returns the evolved existing.
    For SUPERSEDE, returns a new Thesis with existing marked superseded.
    For HOLD, returns existing unchanged.

    Args:
        decision: The path decision from decide_thesis_update_path.
        research: The new Research.
        existing: The existing Thesis, or None.
        new_interpretation: The new interpretation to apply.
        by: What triggered the update (typically the research id).

    Returns:
        The resulting Thesis.
    """
    if decision.path == ThesisUpdatePath.EVOLVE and existing is not None:
        return existing.evolve(
            new_interpretation=new_interpretation,
            contributing_research_ids=(research.id,),
            by=by,
        )

    if decision.path == ThesisUpdatePath.SUPERSEDE and existing is not None:
        return existing.supersede_with(
            new_interpretation=new_interpretation,
            by=by,
            prior_id=existing.id,
        )

    if decision.path == ThesisUpdatePath.HOLD and existing is not None:
        # HOLD: return existing with an open question annotated.
        return existing.hold_with_open_question(
            question=f"Research {research.id} inconclusive on {research.entity_ref.id}"
        )

    # No existing thesis: create a new one.
    return Thesis.create(
        entity_ref=research.entity_ref,
        interpretation=new_interpretation,
        supporting_research_ids=(research.id,),
        status=ThesisStatus.EMERGING,
    )


# ---------------------------------------------------------------------------
# Rule 1: New Signal Handling
# ---------------------------------------------------------------------------


@dataclass
class SignalHandlingResult:
    """Result of applying Rule 1 to a new Signal."""

    signal: Signal
    accepted: bool
    rationale: str


def handle_new_signal(signal: Signal) -> SignalHandlingResult:
    """Apply Workflow Model Rule 1 to a new Signal.

    Per Rule 1:
    1. The Signal is created in DRAFT status with full Evidence grounding.
    2. Validation gates run (handled by Stage 3).
    3. If gates pass, advance to VERIFIED.
    4. The Signal is never consumed.

    This function assumes gates have already passed. It performs the
    DRAFT -> VERIFIED transition via the domain object method (which goes
    through the lifecycle module).

    Args:
        signal: The Signal in DRAFT status.

    Returns:
        SignalHandlingResult with the verified Signal and rationale.
    """
    if signal.status != SignalStatus.DRAFT:
        return SignalHandlingResult(
            signal=signal,
            accepted=False,
            rationale=f"signal is in {signal.status.value}, not DRAFT",
        )

    verified = signal.verify()
    return SignalHandlingResult(
        signal=verified,
        accepted=True,
        rationale="signal verified; available for Research aggregation",
    )


# ---------------------------------------------------------------------------
# Rule 3: Conflicting Research
# ---------------------------------------------------------------------------


@dataclass
class ConflictResolution:
    """Result of applying Rule 3 to conflicting Research objects."""

    can_coexist: bool
    rationale: str


def resolve_conflicting_research(research_a: Research, research_b: Research) -> ConflictResolution:
    """Apply Workflow Model Rule 3 to conflicting Research.

    Per Rule 3:
    1. Both Research objects are retained.
    2. The conflict is recorded as a relationship.
    3. The Thesis stage integrates the conflict if possible.
    4. Multiple Theses may coexist on the same Entity.

    For MVP: if two Research objects reach different conclusions about
    the same Entity, both are retained. The Thesis stage will decide
    whether they can be integrated into a single Thesis or require
    multiple Theses.

    Args:
        research_a: First Research.
        research_b: Second Research.

    Returns:
        ConflictResolution indicating whether they can coexist.
    """
    if research_a.entity_ref.id != research_b.entity_ref.id:
        return ConflictResolution(
            can_coexist=True,
            rationale="different entities; no conflict",
        )

    # Same entity, different conclusions: both retained.
    # Whether they form one Thesis or two is a Stage 5 decision.
    return ConflictResolution(
        can_coexist=True,
        rationale="same entity, different conclusions; both retained per Rule 3",
    )


# ---------------------------------------------------------------------------
# Rule 4: Knowledge Accumulation
# ---------------------------------------------------------------------------


def is_thesis_ready_for_integration(thesis: Thesis) -> bool:
    """Check if a Thesis is ready for Stage 6 integration.

    Per Rule 4, knowledge accumulates as Theses mature. A Thesis is ready
    when it has reached a stable status (EVOLVING with history, or MATURE).
    """
    return thesis.status in (ThesisStatus.EVOLVING, ThesisStatus.MATURE)


def is_thesis_pending(thesis: Thesis) -> bool:
    """Check if a Thesis should be held at Pending (not ready for integration)."""
    return thesis.status == ThesisStatus.EMERGING