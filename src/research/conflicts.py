"""
Conflict surfacing — Phase 5 Checkpoint 2.

Per Runtime Model OQ-7, certain combinations of curator actions and
research-layer events create logical conflicts that must be surfaced
explicitly. This module detects and emits `ConflictEvent` records.

Conflict kinds detected here:

- DUPLICATE_OVERRIDE: the same OverrideAction is applied twice to the
  same target within a short window (e.g., two `mark_noise` actions on
  the same Signal in the same cycle).
- CONFLICTING_OVERRIDE: `add_entity` and `remove_entity` are recorded
  for the same target+entity pair (cancel each other out).
- STALE_OVERRIDE: an `override_score` is followed by a `mark_noise`
  on the same target (the override is moot once the signal is noise).

This module is intentionally conservative: it surfaces only the
conflicts that are detectable from the OverrideRecord log alone. Domain-
specific conflict detection (e.g., cross-research contradictions) lives
in higher layers.

Dependency rules:
- Depends only on `persistence.override.OverrideRecord` and core IDs.
- Does NOT import runtime.* internals.
- Does NOT mutate the Store.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

from src.core.ids import ID
from src.core.timestamps import now_utc
from src.persistence.override import OverrideAction, OverrideRecord


class ConflictKind(str, Enum):
    """Canonical conflict kinds surfaced by ConflictDetector."""

    DUPLICATE_OVERRIDE = "duplicate_override"
    CONFLICTING_OVERRIDE = "conflicting_override"
    STALE_OVERRIDE = "stale_override"


@dataclass(frozen=True, slots=True)
class ConflictEvent:
    """A logical conflict detected from the OverrideRecord log.

    Fields:
        kind: The kind of conflict.
        target_id: The Object ID at the center of the conflict.
        rationale: Human-readable explanation.
        contributing_record_ids: OverrideRecord IDs that together create
            the conflict.
        at: ISO8601 UTC timestamp of detection.
    """

    kind: ConflictKind
    target_id: ID
    rationale: str
    contributing_record_ids: tuple[ID, ...]
    at: str


class ConflictDetector:
    """Inspects the OverrideRecord log and emits ConflictEvents.

    The detector is stateless; callers feed it the OverrideRecords to
    inspect. The detector does not write to the Store.
    """

    def detect(
        self, overrides: Iterable[OverrideRecord]
    ) -> tuple[ConflictEvent, ...]:
        """Run all conflict-detection rules against the given overrides."""
        records = tuple(overrides)
        events: list[ConflictEvent] = []

        events.extend(self._detect_duplicates(records))
        events.extend(self._detect_conflicting_add_remove(records))
        events.extend(self._detect_stale_overrides(records))

        return tuple(events)

    # ---- rule: DUPLICATE_OVERRIDE ----

    def _detect_duplicates(
        self, records: tuple[OverrideRecord, ...]
    ) -> list[ConflictEvent]:
        """Flag pairs (or more) of identical (target_id, action) tuples."""
        events: list[ConflictEvent] = []
        # Group records by (target_id, action).
        groups: dict[tuple[str, OverrideAction], list[OverrideRecord]] = defaultdict(list)
        for r in records:
            key = (str(r.target_id), r.action)
            groups[key].append(r)
        for (target_id, action), group in groups.items():
            # Actions that legitimately may repeat (UPDATE_NOTES) are excluded
            # from this rule — repeating notes is not a conflict.
            if action == OverrideAction.UPDATE_NOTES:
                continue
            if len(group) >= 2:
                events.append(
                    ConflictEvent(
                        kind=ConflictKind.DUPLICATE_OVERRIDE,
                        target_id=ID(target_id),
                        rationale=(
                            f"{action.value!r} applied {len(group)} times to {target_id!r}"
                        ),
                        contributing_record_ids=tuple(r.id for r in group),
                        at=now_utc(),
                    )
                )
        return events

    # ---- rule: CONFLICTING_OVERRIDE (add + remove same entity) ----

    def _detect_conflicting_add_remove(
        self, records: tuple[OverrideRecord, ...]
    ) -> list[ConflictEvent]:
        events: list[ConflictEvent] = []
        # For each target_id, collect entity_ids added vs removed.
        added: dict[str, set[str]] = defaultdict(set)
        removed: dict[str, set[str]] = defaultdict(set)
        contributing: dict[tuple[str, str], list[OverrideRecord]] = defaultdict(list)
        for r in records:
            if r.action not in {
                OverrideAction.ADD_ENTITY,
                OverrideAction.REMOVE_ENTITY,
            }:
                continue
            payload = r.payload or {}
            entity_id_raw = payload.get("entity_id")
            entity_id = str(entity_id_raw) if entity_id_raw else ""
            if not entity_id:
                continue
            target_id = str(r.target_id)
            key = (target_id, entity_id)
            contributing[key].append(r)
            if r.action == OverrideAction.ADD_ENTITY:
                added[target_id].add(entity_id)
            else:
                removed[target_id].add(entity_id)
        for (target_id, entity_id), group in contributing.items():
            if entity_id in added.get(target_id, set()) and entity_id in removed.get(
                target_id, set()
            ):
                events.append(
                    ConflictEvent(
                        kind=ConflictKind.CONFLICTING_OVERRIDE,
                        target_id=ID(target_id),
                        rationale=(
                            f"entity {entity_id!r} both added and removed from "
                            f"target {target_id!r}"
                        ),
                        contributing_record_ids=tuple(r.id for r in group),
                        at=now_utc(),
                    )
                )
        return events

    # ---- rule: STALE_OVERRIDE (override_score then mark_noise) ----

    def _detect_stale_overrides(
        self, records: tuple[OverrideRecord, ...]
    ) -> list[ConflictEvent]:
        events: list[ConflictEvent] = []
        by_target: dict[str, list[OverrideRecord]] = defaultdict(list)
        for r in records:
            by_target[str(r.target_id)].append(r)
        for target_id, group in by_target.items():
            actions = {r.action for r in group}
            if (
                OverrideAction.OVERRIDE_SCORE in actions
                and OverrideAction.MARK_NOISE in actions
            ):
                contributing = [
                    r for r in group
                    if r.action in {
                        OverrideAction.OVERRIDE_SCORE,
                        OverrideAction.MARK_NOISE,
                    }
                ]
                events.append(
                    ConflictEvent(
                        kind=ConflictKind.STALE_OVERRIDE,
                        target_id=ID(target_id),
                        rationale=(
                            f"override_score on {target_id!r} is stale because "
                            f"the same target was also marked noise"
                        ),
                        contributing_record_ids=tuple(r.id for r in contributing),
                        at=now_utc(),
                    )
                )
        return events


__all__ = ["ConflictDetector", "ConflictEvent", "ConflictKind"]