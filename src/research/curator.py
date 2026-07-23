"""
Curator actions — Phase 5 Checkpoint 2.

The `Curator` class implements the 8 canonical curator actions per the
SIGNAL implementation roadmap (§Phase 5, Research Layer):

    1. override_score
    2. mark_noise
    3. mark_redundant
    4. change_tier
    5. add_entity
    6. remove_entity
    7. bind_industry_position
    8. update_notes

Each action:
    - Validates the target Object exists in the abstract `Store`.
    - Builds an `OverrideRecord` (append-only per INV-11).
    - Persists via `Store.append_override`.
    - Returns the `OverrideRecord` (the action's audit trail).

The Curator does NOT mutate domain Objects directly. It only emits
OverrideRecords; downstream consumers (e.g., KnowledgeUpdater on a future
checkpoint) interpret the log and apply effects. This separation keeps the
curator pure and audit-friendly.

Dependency rules:
- Curator depends ONLY on `persistence.store.Store` (abstract interface).
- Curator MUST NOT import runtime.* internals.
- Curator MUST NOT import workflow gates.
- Curator MUST NOT import any concrete persistence backend.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.core.ids import ID
from src.persistence.override import OverrideAction, OverrideRecord

if TYPE_CHECKING:
    from src.persistence.store import Store


class CuratorError(Exception):
    """Base class for curator-action errors."""


class TargetNotFoundError(CuratorError):
    """Raised when a curator action targets an Object that does not exist."""

    def __init__(self, target_id: str, action: OverrideAction) -> None:
        self.target_id = target_id
        self.action = action
        super().__init__(
            f"Curator action {action.value!r} targets unknown Object {target_id!r}"
        )


class InvalidPayloadError(CuratorError):
    """Raised when an action's payload is missing required fields."""

    def __init__(self, action: OverrideAction, missing: str) -> None:
        self.action = action
        self.missing = missing
        super().__init__(
            f"Curator action {action.value!r} missing required payload field: {missing}"
        )


@dataclass(frozen=True, slots=True)
class Curator:
    """Performs curator actions against the abstract Store.

    The Curator holds a reference to the abstract `Store` interface and the
    actor identifier (e.g., "curator:alice"). Each action method produces
    an `OverrideRecord` and appends it via `Store.append_override`.

    The Curator does not enforce business rules about WHICH actions are
    appropriate for which targets; that is the responsibility of the
    workflow layer. The Curator only validates payload completeness and
    target existence.
    """

    store: "Store"
    actor: str = "curator"

    # ---- target existence check ----

    def _target_exists(self, target_id: str) -> bool:
        """Check whether the target Object exists in the Store."""
        sid = str(target_id)
        return (
            self.store.get_entity(sid) is not None
            or self.store.get_source(sid) is not None
            or self.store.get_evidence(sid) is not None
            or self.store.get_signal(sid) is not None
            or self.store.get_research(sid) is not None
            or self.store.get_thesis(sid) is not None
        )

    def _record(
        self,
        *,
        target_id: str,
        action: OverrideAction,
        rationale: str,
        payload: dict[str, object] | None = None,
    ) -> OverrideRecord:
        """Build and append an OverrideRecord.

        Raises:
            TargetNotFoundError: If the target Object is not in the Store.
        """
        if not self._target_exists(target_id):
            raise TargetNotFoundError(target_id, action)
        record = OverrideRecord.create(
            target_id=ID(target_id),
            action=action,
            rationale=rationale,
            actor=self.actor,
            payload=payload,
        )
        self.store.append_override(record)
        return record

    # ---- 1. override_score ----

    def override_score(
        self,
        target_id: str,
        *,
        new_composite: float,
        rationale: str,
    ) -> OverrideRecord:
        """Override a Signal's composite score.

        Args:
            target_id: The Signal's ID.
            new_composite: Replacement composite score in [0.0, 1.0].
            rationale: Why the override is being applied.

        Returns:
            The appended `OverrideRecord`.

        Raises:
            InvalidPayloadError: If `new_composite` is out of [0.0, 1.0].
            TargetNotFoundError: If `target_id` is not a known Signal.
        """
        if not (0.0 <= new_composite <= 1.0):
            raise InvalidPayloadError(
                OverrideAction.OVERRIDE_SCORE,
                f"new_composite={new_composite} not in [0.0, 1.0]",
            )
        return self._record(
            target_id=target_id,
            action=OverrideAction.OVERRIDE_SCORE,
            rationale=rationale,
            payload={"new_composite": new_composite},
        )

    # ---- 2. mark_noise ----

    def mark_noise(
        self,
        target_id: str,
        *,
        rationale: str,
    ) -> OverrideRecord:
        """Mark a Signal as noise."""
        return self._record(
            target_id=target_id,
            action=OverrideAction.MARK_NOISE,
            rationale=rationale,
        )

    # ---- 3. mark_redundant ----

    def mark_redundant(
        self,
        target_id: str,
        *,
        redundant_with_id: str,
        rationale: str,
    ) -> OverrideRecord:
        """Mark a Signal as redundant with another Signal.

        Args:
            target_id: The Signal's ID.
            redundant_with_id: The ID of the canonical Signal that this
                one duplicates.
            rationale: Why the redundancy is asserted.
        """
        if not redundant_with_id:
            raise InvalidPayloadError(
                OverrideAction.MARK_REDUNDANT, "redundant_with_id"
            )
        return self._record(
            target_id=target_id,
            action=OverrideAction.MARK_REDUNDANT,
            rationale=rationale,
            payload={"redundant_with_id": str(redundant_with_id)},
        )

    # ---- 4. change_tier ----

    def change_tier(
        self,
        target_id: str,
        *,
        new_tier: str,
        rationale: str,
    ) -> OverrideRecord:
        """Change an Entity's watchlist tier.

        `new_tier` is a free-form string (e.g., "tier_1", "tier_2",
        "unwatched"). Domain-specific tier vocabularies live elsewhere;
        the Curator only records the change.
        """
        if not new_tier:
            raise InvalidPayloadError(OverrideAction.CHANGE_TIER, "new_tier")
        return self._record(
            target_id=target_id,
            action=OverrideAction.CHANGE_TIER,
            rationale=rationale,
            payload={"new_tier": new_tier},
        )

    # ---- 5. add_entity ----

    def add_entity(
        self,
        target_id: str,
        *,
        entity_id: str,
        rationale: str,
    ) -> OverrideRecord:
        """Add an Entity to a Research or Thesis."""
        if not entity_id:
            raise InvalidPayloadError(OverrideAction.ADD_ENTITY, "entity_id")
        return self._record(
            target_id=target_id,
            action=OverrideAction.ADD_ENTITY,
            rationale=rationale,
            payload={"entity_id": str(entity_id)},
        )

    # ---- 6. remove_entity ----

    def remove_entity(
        self,
        target_id: str,
        *,
        entity_id: str,
        rationale: str,
    ) -> OverrideRecord:
        """Remove an Entity from a Research or Thesis."""
        if not entity_id:
            raise InvalidPayloadError(OverrideAction.REMOVE_ENTITY, "entity_id")
        return self._record(
            target_id=target_id,
            action=OverrideAction.REMOVE_ENTITY,
            rationale=rationale,
            payload={"entity_id": str(entity_id)},
        )

    # ---- 7. bind_industry_position ----

    def bind_industry_position(
        self,
        target_id: str,
        *,
        industry_position: str,
        rationale: str,
    ) -> OverrideRecord:
        """Bind an Entity to an industry position (e.g., "leader", "niche")."""
        if not industry_position:
            raise InvalidPayloadError(
                OverrideAction.BIND_INDUSTRY_POSITION, "industry_position"
            )
        return self._record(
            target_id=target_id,
            action=OverrideAction.BIND_INDUSTRY_POSITION,
            rationale=rationale,
            payload={"industry_position": industry_position},
        )

    # ---- 8. update_notes ----

    def update_notes(
        self,
        target_id: str,
        *,
        notes: str,
        rationale: str,
    ) -> OverrideRecord:
        """Update curator notes for an Object."""
        if not notes:
            raise InvalidPayloadError(OverrideAction.UPDATE_NOTES, "notes")
        return self._record(
            target_id=target_id,
            action=OverrideAction.UPDATE_NOTES,
            rationale=rationale,
            payload={"notes": notes},
        )


__all__ = [
    "Curator",
    "CuratorError",
    "InvalidPayloadError",
    "TargetNotFoundError",
]