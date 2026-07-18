"""
Lifecycle state machines for SIGNAL objects.

Each Object type has a defined lifecycle (a set of states and the allowed
transitions between them). Transitions are validated centrally in this module
so that all types share consistent error handling and INV-6 is enforced.

INVARIANT: Lifecycle transitions MUST follow the allowed graph (INV-6).
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import Enum
from typing import TypeVar

# A generic state type for lifecycle enums.
StateT = TypeVar("StateT", bound=Enum)


class LifecycleError(Exception):
    """Raised when a lifecycle transition is invalid."""

    def __init__(self, current: str, target: str, allowed: Iterable[str]) -> None:
        self.current = current
        self.target = target
        self.allowed = list(allowed)
        super().__init__(
            f"Invalid transition: {current!r} -> {target!r}. "
            f"Allowed targets from {current!r}: {self.allowed}"
        )


def can_transition(
    allowed_graph: dict[StateT, frozenset[StateT]],
    current: StateT,
    target: StateT,
) -> bool:
    """Check if a transition is allowed.

    Args:
        allowed_graph: A mapping from state to its set of valid target states.
        current: The current state.
        target: The proposed target state.

    Returns:
        True if the transition is in the graph, False otherwise.
    """
    if current not in allowed_graph:
        return False
    return target in allowed_graph[current]


def assert_transition(
    allowed_graph: dict[StateT, frozenset[StateT]],
    current: StateT,
    target: StateT,
) -> None:
    """Assert that a transition is allowed; raise LifecycleError if not."""
    allowed = allowed_graph.get(current, frozenset())
    if target not in allowed:
        raise LifecycleError(current.value, target.value, [s.value for s in allowed])


def terminal_states(allowed_graph: dict[StateT, frozenset[StateT]]) -> frozenset[StateT]:
    """Return the set of terminal states (states with no outgoing transitions)."""
    return frozenset(state for state, targets in allowed_graph.items() if not targets)


# ---------------------------------------------------------------------------
# Per-type lifecycle graphs
# ---------------------------------------------------------------------------
# Each graph maps a state to its allowed target states. Terminal states
# have an empty frozenset. Self-transitions are NOT included by default; add
# them explicitly if a type allows "stay in the same state" transitions.


# Signal lifecycle (per Workflow Model and Object Model Decision 1).
# draft -> verified -> active -> {decayed | superseded}
# draft -> rejected (early rejection)
# verified -> {held | rejected}
# active -> {decayed | superseded}
# held -> {active | rejected}
from enum import Enum as _Enum


class SignalStatus(str, _Enum):
    """Signal lifecycle status."""

    DRAFT = "draft"
    VERIFIED = "verified"
    ACTIVE = "active"
    HELD = "held"
    REJECTED = "rejected"
    DECAYED = "decayed"
    SUPERSEDED = "superseded"


SIGNAL_LIFECYCLE: dict[SignalStatus, frozenset[SignalStatus]] = {
    SignalStatus.DRAFT: frozenset({SignalStatus.VERIFIED, SignalStatus.REJECTED}),
    SignalStatus.VERIFIED: frozenset({SignalStatus.ACTIVE, SignalStatus.HELD, SignalStatus.REJECTED}),
    SignalStatus.ACTIVE: frozenset({SignalStatus.DECAYED, SignalStatus.SUPERSEDED}),
    SignalStatus.HELD: frozenset({SignalStatus.ACTIVE, SignalStatus.REJECTED}),
    SignalStatus.REJECTED: frozenset(),
    SignalStatus.DECAYED: frozenset(),
    SignalStatus.SUPERSEDED: frozenset(),
}


# Thesis lifecycle (per Object Model §6).
# emerging -> evolving -> mature -> {superseded | retired}
# mature -> evolving (reopened)
# emerging -> superseded (rare)
class ThesisStatus(str, _Enum):
    """Thesis lifecycle status."""

    EMERGING = "emerging"
    EVOLVING = "evolving"
    MATURE = "mature"
    SUPERSEDED = "superseded"
    RETIRED = "retired"


THESIS_LIFECYCLE: dict[ThesisStatus, frozenset[ThesisStatus]] = {
    ThesisStatus.EMERGING: frozenset({ThesisStatus.EVOLVING, ThesisStatus.SUPERSEDED}),
    ThesisStatus.EVOLVING: frozenset({ThesisStatus.MATURE, ThesisStatus.SUPERSEDED, ThesisStatus.RETIRED}),
    ThesisStatus.MATURE: frozenset({ThesisStatus.EVOLVING, ThesisStatus.SUPERSEDED, ThesisStatus.RETIRED}),
    ThesisStatus.SUPERSEDED: frozenset(),
    ThesisStatus.RETIRED: frozenset(),
}


# Research lifecycle.
# open -> ongoing -> concluded
# open -> paused
# ongoing -> {concluded | paused}
class ResearchStatus(str, _Enum):
    """Research lifecycle status."""

    OPEN = "open"
    ONGOING = "ongoing"
    PAUSED = "paused"
    CONCLUDED = "concluded"


RESEARCH_LIFECYCLE: dict[ResearchStatus, frozenset[ResearchStatus]] = {
    ResearchStatus.OPEN: frozenset({ResearchStatus.ONGOING, ResearchStatus.PAUSED, ResearchStatus.CONCLUDED}),
    ResearchStatus.ONGOING: frozenset({ResearchStatus.PAUSED, ResearchStatus.CONCLUDED}),
    ResearchStatus.PAUSED: frozenset({ResearchStatus.ONGOING, ResearchStatus.CONCLUDED}),
    ResearchStatus.CONCLUDED: frozenset(),
}


# Source lifecycle.
# active -> {deactivated | retired}
# deactivated -> {active | retired}
class SourceStatus(str, _Enum):
    """Source lifecycle status."""

    ACTIVE = "active"
    DEACTIVATED = "deactivated"
    RETIRED = "retired"


SOURCE_LIFECYCLE: dict[SourceStatus, frozenset[SourceStatus]] = {
    SourceStatus.ACTIVE: frozenset({SourceStatus.DEACTIVATED, SourceStatus.RETIRED}),
    SourceStatus.DEACTIVATED: frozenset({SourceStatus.ACTIVE, SourceStatus.RETIRED}),
    SourceStatus.RETIRED: frozenset(),
}
