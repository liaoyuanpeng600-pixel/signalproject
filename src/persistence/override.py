"""
OverrideRecord — curator action audit entries (INV-11).

OverrideRecords are APPEND-ONLY. They record curator actions (override, mark
noise, change tier, etc.) against a target Object. They cannot be modified or
deleted once appended; they are part of the immutable audit trail.

This module defines the OverrideRecord type and the canonical set of curator
actions. The full curator interface (with 8 actions) lives in Phase 5
(Research Layer). For MVP persistence, we define the data shape so that
OverrideRecords can be persisted even before the curator surface is built.

INVARIANTS:
- INV-11: OverrideRecord append-only (enforced by InMemoryStore.append_override).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from src.core.ids import ID, new_id
from src.core.timestamps import now_utc


class OverrideAction(str, Enum):
    """Canonical curator actions that produce an OverrideRecord.

    MVP subset. Phase 5 may extend this set; new values are added, never removed
    (existing records must remain interpretable).
    """

    OVERRIDE_SCORE = "override_score"
    MARK_NOISE = "mark_noise"
    MARK_REDUNDANT = "mark_redundant"
    CHANGE_TIER = "change_tier"
    ADD_ENTITY = "add_entity"
    REMOVE_ENTITY = "remove_entity"
    BIND_INDUSTRY_POSITION = "bind_industry_position"
    UPDATE_NOTES = "update_notes"


@dataclass(frozen=True, slots=True)
class OverrideRecord:
    """An immutable record of a curator action.

    Fields:
        id: Unique identifier for this record.
        target_id: ID of the Object being acted upon.
        action: The curator action taken.
        rationale: Human-readable explanation. Required (non-empty).
        actor: Identifier of the curator or system component taking the action.
        payload: Action-specific structured data (e.g., new score values).
        at: ISO8601 UTC timestamp.
    """

    id: ID
    target_id: ID
    action: OverrideAction
    rationale: str
    actor: str
    at: str
    payload: dict[str, object] | None = None

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("OverrideRecord.id is required")
        if not self.target_id:
            raise ValueError("OverrideRecord.target_id is required")
        if not self.rationale:
            raise ValueError("OverrideRecord.rationale is required")
        if not self.actor:
            raise ValueError("OverrideRecord.actor is required")

    @classmethod
    def create(
        cls,
        target_id: ID,
        action: OverrideAction,
        rationale: str,
        actor: str,
        payload: dict[str, object] | None = None,
        id: ID | None = None,
        at: str | None = None,
    ) -> "OverrideRecord":
        """Factory method to create a new OverrideRecord with auto-generated ID."""
        return cls(
            id=id if id is not None else new_id(),
            target_id=target_id,
            action=action,
            rationale=rationale,
            actor=actor,
            payload=payload,
            at=at if at is not None else now_utc(),
        )