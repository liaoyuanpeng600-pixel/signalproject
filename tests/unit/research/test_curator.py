"""Tests for Curator (Phase 5 Checkpoint 2)."""

import pytest

from src.core.entities import Entity, EntityKind
from src.core.ids import ID
from src.core.invariants import Score
from src.core.lifecycle import SignalStatus
from src.core.signals import EntityRef, Signal, SignalDirection, SignalHorizon
from src.persistence.in_memory import InMemoryStore
from src.persistence.override import OverrideAction
from src.persistence.store import Store
from src.research.curator import (
    Curator,
    InvalidPayloadError,
    TargetNotFoundError,
)


# ----------------------- helpers -----------------------


def _seeded_store() -> Store:
    """Store containing one Entity and one ACTIVE Signal."""
    store = InMemoryStore()
    entity = Entity.create(kind=EntityKind.COMPANY, name="ACME")
    signal = Signal.create(
        entity_ref=EntityRef(id=entity.id, kind=entity.kind.value),
        type="capital_action",
        claim="ACME dividend up 10%",
        evidence_ids=(ID("ev-1"),),
        direction=SignalDirection.BULLISH,
        horizon=SignalHorizon.SHORT,
        score=Score(0.7, 0.7, 0.7, 0.7, 0.7),
        status=SignalStatus.ACTIVE,
    )
    store.put_entity(entity)
    store.put_signal(signal)
    return store, entity, signal


# ----------------------- constructor / basic API -----------------------


class TestCuratorBasics:
    def test_curator_constructor(self) -> None:
        store, entity, _ = _seeded_store()
        curator = Curator(store=store, actor="curator:alice")
        assert curator.actor == "curator:alice"
        assert curator.store is store

    def test_default_actor(self) -> None:
        store, _, _ = _seeded_store()
        curator = Curator(store=store)
        assert curator.actor == "curator"

    def test_actor_is_recorded(self) -> None:
        store, entity, _ = _seeded_store()
        curator = Curator(store=store, actor="curator:bob")
        rec = curator.change_tier(str(entity.id), new_tier="tier_1", rationale="r")
        assert rec.actor == "curator:bob"


# ----------------------- 1. override_score -----------------------


class TestOverrideScore:
    def test_records_override(self) -> None:
        store, _, signal = _seeded_store()
        curator = Curator(store=store)
        rec = curator.override_score(
            str(signal.id), new_composite=0.4, rationale="manual adjustment"
        )
        assert rec.action == OverrideAction.OVERRIDE_SCORE
        assert rec.payload == {"new_composite": 0.4}
        assert rec.rationale == "manual adjustment"
        assert store.list_overrides() == (rec,)

    def test_rejects_out_of_range_composite(self) -> None:
        store, _, signal = _seeded_store()
        curator = Curator(store=store)
        with pytest.raises(InvalidPayloadError):
            curator.override_score(str(signal.id), new_composite=1.5, rationale="r")
        with pytest.raises(InvalidPayloadError):
            curator.override_score(str(signal.id), new_composite=-0.1, rationale="r")

    def test_rejects_unknown_target(self) -> None:
        store, _, _ = _seeded_store()
        curator = Curator(store=store)
        with pytest.raises(TargetNotFoundError):
            curator.override_score("nonexistent", new_composite=0.5, rationale="r")


# ----------------------- 2. mark_noise -----------------------


class TestMarkNoise:
    def test_records_noise(self) -> None:
        store, _, signal = _seeded_store()
        curator = Curator(store=store)
        rec = curator.mark_noise(str(signal.id), rationale="irrelevant")
        assert rec.action == OverrideAction.MARK_NOISE
        assert rec.payload is None


# ----------------------- 3. mark_redundant -----------------------


class TestMarkRedundant:
    def test_records_redundant(self) -> None:
        store, _, signal = _seeded_store()
        # Need a second signal so we have a valid "redundant_with" target.
        sig2 = Signal.create(
            entity_ref=signal.entity_ref,
            type=signal.type,
            claim="dup claim",
            evidence_ids=(ID("ev-2"),),
            direction=signal.direction,
            horizon=signal.horizon,
            score=signal.score,
            status=SignalStatus.ACTIVE,
            id=ID("sig-2"),
        )
        store.put_signal(sig2)
        curator = Curator(store=store)
        rec = curator.mark_redundant(
            str(signal.id),
            redundant_with_id=str(sig2.id),
            rationale="duplicate of sig-2",
        )
        assert rec.action == OverrideAction.MARK_REDUNDANT
        assert rec.payload == {"redundant_with_id": str(sig2.id)}

    def test_rejects_empty_redundant_with(self) -> None:
        store, _, signal = _seeded_store()
        curator = Curator(store=store)
        with pytest.raises(InvalidPayloadError):
            curator.mark_redundant(
                str(signal.id), redundant_with_id="", rationale="r"
            )


# ----------------------- 4. change_tier -----------------------


class TestChangeTier:
    def test_records_tier_change(self) -> None:
        store, entity, _ = _seeded_store()
        curator = Curator(store=store)
        rec = curator.change_tier(
            str(entity.id), new_tier="tier_2", rationale="deprioritized"
        )
        assert rec.action == OverrideAction.CHANGE_TIER
        assert rec.payload == {"new_tier": "tier_2"}

    def test_rejects_empty_tier(self) -> None:
        store, entity, _ = _seeded_store()
        curator = Curator(store=store)
        with pytest.raises(InvalidPayloadError):
            curator.change_tier(str(entity.id), new_tier="", rationale="r")


# ----------------------- 5. add_entity -----------------------


class TestAddEntity:
    def test_records_add(self) -> None:
        store, entity, signal = _seeded_store()
        curator = Curator(store=store)
        rec = curator.add_entity(
            str(signal.id),
            entity_id=str(entity.id),
            rationale="add to research",
        )
        assert rec.action == OverrideAction.ADD_ENTITY
        assert rec.payload == {"entity_id": str(entity.id)}

    def test_rejects_empty_entity(self) -> None:
        store, _, signal = _seeded_store()
        curator = Curator(store=store)
        with pytest.raises(InvalidPayloadError):
            curator.add_entity(str(signal.id), entity_id="", rationale="r")


# ----------------------- 6. remove_entity -----------------------


class TestRemoveEntity:
    def test_records_remove(self) -> None:
        store, entity, signal = _seeded_store()
        curator = Curator(store=store)
        rec = curator.remove_entity(
            str(signal.id),
            entity_id=str(entity.id),
            rationale="mis-attributed",
        )
        assert rec.action == OverrideAction.REMOVE_ENTITY
        assert rec.payload == {"entity_id": str(entity.id)}


# ----------------------- 7. bind_industry_position -----------------------


class TestBindIndustryPosition:
    def test_records_position(self) -> None:
        store, entity, _ = _seeded_store()
        curator = Curator(store=store)
        rec = curator.bind_industry_position(
            str(entity.id),
            industry_position="niche_leader",
            rationale="specialty positioning",
        )
        assert rec.action == OverrideAction.BIND_INDUSTRY_POSITION
        assert rec.payload == {"industry_position": "niche_leader"}

    def test_rejects_empty_position(self) -> None:
        store, entity, _ = _seeded_store()
        curator = Curator(store=store)
        with pytest.raises(InvalidPayloadError):
            curator.bind_industry_position(
                str(entity.id), industry_position="", rationale="r"
            )


# ----------------------- 8. update_notes -----------------------


class TestUpdateNotes:
    def test_records_notes(self) -> None:
        store, entity, _ = _seeded_store()
        curator = Curator(store=store)
        rec = curator.update_notes(
            str(entity.id),
            notes="re-evaluated after Q3 earnings",
            rationale="context update",
        )
        assert rec.action == OverrideAction.UPDATE_NOTES
        assert rec.payload == {"notes": "re-evaluated after Q3 earnings"}

    def test_rejects_empty_notes(self) -> None:
        store, entity, _ = _seeded_store()
        curator = Curator(store=store)
        with pytest.raises(InvalidPayloadError):
            curator.update_notes(str(entity.id), notes="", rationale="r")


# ----------------------- target-existence checks -----------------------


class TestTargetExistence:
    def test_target_can_be_entity(self) -> None:
        store, entity, _ = _seeded_store()
        curator = Curator(store=store)
        rec = curator.change_tier(str(entity.id), new_tier="tier_1", rationale="r")
        assert rec.target_id == entity.id

    def test_target_can_be_signal(self) -> None:
        store, _, signal = _seeded_store()
        curator = Curator(store=store)
        rec = curator.mark_noise(str(signal.id), rationale="r")
        assert rec.target_id == signal.id

    def test_unknown_target_raises(self) -> None:
        store, _, _ = _seeded_store()
        curator = Curator(store=store)
        with pytest.raises(TargetNotFoundError):
            curator.mark_noise("nonexistent-id", rationale="r")

    def test_overrides_are_appended_not_replaced(self) -> None:
        """INV-11: OverrideRecord log is append-only."""
        store, _, signal = _seeded_store()
        curator = Curator(store=store)
        r1 = curator.mark_noise(str(signal.id), rationale="r1")
        r2 = curator.mark_noise(str(signal.id), rationale="r2")
        log = store.list_overrides()
        assert len(log) == 2
        assert log[0] is r1
        assert log[1] is r2


# ----------------------- dep-inversion -----------------------


class TestCuratorDepInversion:
    def test_curator_does_not_import_runtime(self) -> None:
        import re

        import src.research.curator as mod

        source = mod.__file__ or ""
        with open(source, encoding="utf-8") as f:
            contents = f.read()
        assert not re.search(r"^\s*from\s+src\.runtime", contents, re.MULTILINE)
        assert "from src.workflow.gates" not in contents
        assert "from src.workflow.stages" not in contents

    def test_curator_does_not_import_concrete_store(self) -> None:
        import re

        import src.research.curator as mod

        source = mod.__file__ or ""
        with open(source, encoding="utf-8") as f:
            contents = f.read()
        import_re = re.compile(
            r"^\s*(?:from\s+src\.persistence\.in_memory|import\s+src\.persistence\.in_memory)",
            re.MULTILINE,
        )
        assert not import_re.search(contents)