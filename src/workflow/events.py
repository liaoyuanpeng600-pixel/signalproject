"""
Workflow events for decoupling.

Events are emitted by the workflow at key transitions. Consumers (Audit Logger,
Runtime, etc.) subscribe to events without coupling to the workflow internals.

Per the user constraint: "Prefer events and interfaces over tight coupling."

Event types:
- StageStarted: emitted when a stage begins
- GateEvaluated: emitted when a gate is evaluated
- StageCompleted: emitted when a stage completes
- ObjectRouted: emitted when an Object is routed to a failure path
- WorkflowCompleted: emitted when the cycle completes
- WorkflowAborted: emitted when the cycle is aborted (infrastructure failure)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union

from src.core.ids import ID
from src.workflow.types import StageStatus


@dataclass(frozen=True)
class StageStarted:
    """Emitted when a stage begins execution."""

    cycle_id: ID
    stage_name: str
    started_at: str


@dataclass(frozen=True)
class GateEvaluated:
    """Emitted when a gate is evaluated."""

    cycle_id: ID
    stage_name: str
    gate_id: str
    passed: bool
    reason: str | None
    evaluated_at: str


@dataclass(frozen=True)
class StageCompleted:
    """Emitted when a stage completes."""

    cycle_id: ID
    stage_name: str
    status: StageStatus
    completed_at: str


@dataclass(frozen=True)
class ObjectRouted:
    """Emitted when an Object is routed to a failure path."""

    cycle_id: ID
    stage_name: str
    object_id: ID
    object_kind: str  # "evidence", "signal", "research", "thesis", "source", "candidate"
    destination: str  # FailurePath value
    reason: str
    routed_at: str


@dataclass(frozen=True)
class WorkflowCompleted:
    """Emitted when the workflow cycle completes successfully."""

    cycle_id: ID
    started_at: str
    completed_at: str
    signals_emitted: int
    research_emitted: int
    theses_updated: int


@dataclass(frozen=True)
class WorkflowAborted:
    """Emitted when the workflow cycle is aborted (infrastructure failure)."""

    cycle_id: ID
    stage_name: str
    reason: str
    aborted_at: str


# Union type for all workflow events
WorkflowEvent = Union[
    StageStarted,
    GateEvaluated,
    StageCompleted,
    ObjectRouted,
    WorkflowCompleted,
    WorkflowAborted,
]