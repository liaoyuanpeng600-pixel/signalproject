"""Tests for ConflictDetector (Phase 5 Checkpoint 2)."""

import pytest

from src.core.ids import ID
from src.persistence.override import OverrideAction, OverrideRecord
from src.research.conflicts import (
    ConflictDetector,
    ConflictEvent,
    ConflictKind,
)


def _record(
    *,
    target_id: str,
    action: OverrideAction,
    actor: str = "curator:alice",
    rationale: str = "test",
    payload: dict[str, object] | None = None,
) -> OverrideRecord:
    return OverrideRecord.create(
        target_id=ID(target_id),
        action=action,
        rationale=rationale,
        actor=actor,
        payload=payload,
    )


# ----------------------- DUPLICATE_OVERRIDE -----------------------


class TestDuplicateOverride:
    def test_two_identical_actions_flag_conflict(self) -> None:
        r1 = _record(target_id="sig-1", action=OverrideAction.MARK_NOISE)
        r2 = _record(target_id="sig-1", action=OverrideAction.MARK_NOISE, rationale="r2")
        events = ConflictDetector().detect((r1, r2))
        assert len(events) == 1
        e = events[0]
        assert e.kind == ConflictKind.DUPLICATE_OVERRIDE
        assert e.target_id == ID("sig-1")
        assert r1.id in e.contributing_record_ids
        assert r2.id in e.contributing_record_ids

    def test_distinct_targets_no_conflict(self) -> None:
        r1 = _record(target_id="sig-1", action=OverrideAction.MARK_NOISE)
        r2 = _record(target_id="sig-2", action=OverrideAction.MARK_NOISE)
        events = ConflictDetector().detect((r1, r2))
        assert events == ()

    def test_distinct_actions_no_conflict(self) -> None:
        r1 = _record(target_id="sig-1", action=OverrideAction.MARK_NOISE)
        r2 = _record(target_id="sig-1", action=OverrideAction.MARK_REDUNDANT,
                     payload={"redundant_with_id": "sig-x"})
        events = ConflictDetector().detect((r1, r2))
        assert events == ()

    def test_update_notes_is_exempt_from_duplicate_rule(self) -> None:
        """Repeated UPDATE_NOTES is not a conflict (notes are append-style)."""
        r1 = _record(target_id="ent-1", action=OverrideAction.UPDATE_NOTES,
                     payload={"notes": "v1"})
        r2 = _record(target_id="ent-1", action=OverrideAction.UPDATE_NOTES,
                     payload={"notes": "v2"})
        events = ConflictDetector().detect((r1, r2))
        assert events == ()

    def test_three_duplicates_one_event(self) -> None:
        records = tuple(
            _record(target_id="sig-1", action=OverrideAction.MARK_NOISE,
                    rationale=f"r{i}")
            for i in range(3)
        )
        events = ConflictDetector().detect(records)
        assert len(events) == 1
        assert len(events[0].contributing_record_ids) == 3


# ----------------------- CONFLICTING_OVERRIDE -----------------------


class TestConflictingAddRemove:
    def test_add_then_remove_same_entity_flags_conflict(self) -> None:
        r1 = _record(target_id="res-1", action=OverrideAction.ADD_ENTITY,
                     payload={"entity_id": "ent-1"})
        r2 = _record(target_id="res-1", action=OverrideAction.REMOVE_ENTITY,
                     payload={"entity_id": "ent-1"})
        events = ConflictDetector().detect((r1, r2))
        assert len(events) == 1
        e = events[0]
        assert e.kind == ConflictKind.CONFLICTING_OVERRIDE
        assert e.target_id == ID("res-1")
        assert "ent-1" in e.rationale

    def test_add_only_no_conflict(self) -> None:
        r1 = _record(target_id="res-1", action=OverrideAction.ADD_ENTITY,
                     payload={"entity_id": "ent-1"})
        events = ConflictDetector().detect((r1,))
        assert events == ()

    def test_different_entities_no_conflict(self) -> None:
        r1 = _record(target_id="res-1", action=OverrideAction.ADD_ENTITY,
                     payload={"entity_id": "ent-1"})
        r2 = _record(target_id="res-1", action=OverrideAction.REMOVE_ENTITY,
                     payload={"entity_id": "ent-2"})
        events = ConflictDetector().detect((r1, r2))
        assert events == ()

    def test_different_targets_no_conflict(self) -> None:
        r1 = _record(target_id="res-1", action=OverrideAction.ADD_ENTITY,
                     payload={"entity_id": "ent-1"})
        r2 = _record(target_id="res-2", action=OverrideAction.REMOVE_ENTITY,
                     payload={"entity_id": "ent-1"})
        events = ConflictDetector().detect((r1, r2))
        assert events == ()


# ----------------------- STALE_OVERRIDE -----------------------


class TestStaleOverride:
    def test_override_score_then_mark_noise_flags_conflict(self) -> None:
        r1 = _record(target_id="sig-1", action=OverrideAction.OVERRIDE_SCORE,
                     payload={"new_composite": 0.3})
        r2 = _record(target_id="sig-1", action=OverrideAction.MARK_NOISE)
        events = ConflictDetector().detect((r1, r2))
        assert len(events) == 1
        e = events[0]
        assert e.kind == ConflictKind.STALE_OVERRIDE
        assert e.target_id == ID("sig-1")

    def test_mark_noise_only_no_stale_conflict(self) -> None:
        r1 = _record(target_id="sig-1", action=OverrideAction.MARK_NOISE)
        events = ConflictDetector().detect((r1,))
        assert events == ()

    def test_override_score_only_no_stale_conflict(self) -> None:
        r1 = _record(target_id="sig-1", action=OverrideAction.OVERRIDE_SCORE,
                     payload={"new_composite": 0.3})
        events = ConflictDetector().detect((r1,))
        assert events == ()


# ----------------------- composite / multi-rule -----------------------


class TestMultipleRulesTogether:
    def test_two_distinct_conflicts_detected(self) -> None:
        records = (
            _record(target_id="sig-1", action=OverrideAction.MARK_NOISE, rationale="a"),
            _record(target_id="sig-1", action=OverrideAction.MARK_NOISE, rationale="b"),
            _record(target_id="res-1", action=OverrideAction.ADD_ENTITY,
                    payload={"entity_id": "ent-1"}),
            _record(target_id="res-1", action=OverrideAction.REMOVE_ENTITY,
                    payload={"entity_id": "ent-1"}),
        )
        events = ConflictDetector().detect(records)
        kinds = {e.kind for e in events}
        assert ConflictKind.DUPLICATE_OVERRIDE in kinds
        assert ConflictKind.CONFLICTING_OVERRIDE in kinds

    def test_empty_input(self) -> None:
        events = ConflictDetector().detect(())
        assert events == ()


# ----------------------- ConflictEvent properties -----------------------


class TestConflictEvent:
    def test_event_is_frozen(self) -> None:
        e = ConflictEvent(
            kind=ConflictKind.DUPLICATE_OVERRIDE,
            target_id=ID("sig-1"),
            rationale="r",
            contributing_record_ids=(ID("r1"),),
            at="2026-07-19T00:00:00Z",
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            e.rationale = "new"  # type: ignore[misc]


# ----------------------- dep-inversion -----------------------


class TestConflictDepInversion:
    def test_conflicts_does_not_import_runtime(self) -> None:
        import re

        import src.research.conflicts as mod

        source = mod.__file__ or ""
        with open(source, encoding="utf-8") as f:
            contents = f.read()
        assert not re.search(r"^\s*from\s+src\.runtime", contents, re.MULTILINE)

    def test_conflicts_does_not_import_concrete_store(self) -> None:
        import re

        import src.research.conflicts as mod

        source = mod.__file__ or ""
        with open(source, encoding="utf-8") as f:
            contents = f.read()
        import_re = re.compile(
            r"^\s*(?:from\s+src\.persistence\.in_memory|import\s+src\.persistence\.in_memory)",
            re.MULTILINE,
        )
        assert not import_re.search(contents)