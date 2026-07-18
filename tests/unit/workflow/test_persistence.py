"""Tests for workflow.persistence."""

import pytest

from src.core.entities import Entity, EntityKind
from src.core.evidence import Evidence, Quality
from src.core.ids import new_id
from src.core.invariants import Score
from src.core.lifecycle import LifecycleError
from src.core.research import Research
from src.core.signals import (
    EntityRef,
    Signal,
    SignalDirection,
    SignalHorizon,
    SignalStatus,
)
from src.core.sources import Source, SourceType
from src.core.theses import Thesis
from src.workflow.persistence import InMemoryPersistence, Persistence


class TestInMemoryPersistenceImplementsInterface:
    def test_is_persistence(self) -> None:
        p = InMemoryPersistence()
        assert isinstance(p, Persistence)


def make_source() -> Source:
    return Source.create(type=SourceType.NEWS_ARTICLE, url="https://x.com", name="X")


def make_entity() -> Entity:
    return Entity.create(kind=EntityKind.COMPANY, name="ACME")


def make_evidence(source_id) -> Evidence:
    return Evidence.create(
        source_ids=(source_id,),
        content="ACME content",
        quality=Quality(0.9, 0.9, 0.9),
    )


def make_signal() -> Signal:
    return Signal.create(
        entity_ref=EntityRef(id="entity-1", kind="company"),
        type="earnings",
        claim="ACME reported EPS of $1.20.",
        evidence_ids=("ev-1",),
        direction=SignalDirection.BULLISH,
        horizon=SignalHorizon.SHORT,
        score=Score(0.7, 0.9, 0.8, 0.6, 0.75),
        status=SignalStatus.ACTIVE,
    )


def make_research() -> Research:
    return Research.create(
        entity_ref=EntityRef(id="entity-1", kind="company"),
        question="Is ACME undervalued?",
        signal_ids=("sig-1",),
    )


def make_thesis() -> Thesis:
    return Thesis.create(
        entity_ref=EntityRef(id="entity-1", kind="company"),
        interpretation="ACME is undervalued.",
    )


class TestSourceCRUD:
    def test_save_and_get(self) -> None:
        p = InMemoryPersistence()
        source = make_source()
        p.save_source(source)
        assert p.get_source(source.id) is source

    def test_get_nonexistent(self) -> None:
        p = InMemoryPersistence()
        assert p.get_source(new_id()) is None


class TestEntityCRUD:
    def test_save_and_get(self) -> None:
        p = InMemoryPersistence()
        entity = make_entity()
        p.save_entity(entity)
        assert p.get_entity(entity.id) is entity


class TestEvidenceCRUD:
    def test_save_and_get(self) -> None:
        p = InMemoryPersistence()
        source = make_source()
        ev = make_evidence(source.id)
        p.save_evidence(ev)
        assert p.get_evidence(ev.id) is ev

    def test_overwrite_evidence_with_same_id(self) -> None:
        # Evidence is immutable; same ID means same evidence.
        # Persistence can update the record (idempotent).
        p = InMemoryPersistence()
        ev = make_evidence(new_id())
        p.save_evidence(ev)
        # Mark as non-retrievable; produces a new Evidence with same ID
        updated = ev.mark_non_retrievable()
        assert updated.id == ev.id
        p.save_evidence(updated)
        retrieved = p.get_evidence(ev.id)
        assert retrieved.retrievable is False


class TestSignalCRUD:
    def test_save_and_get(self) -> None:
        p = InMemoryPersistence()
        sig = make_signal()
        p.save_signal(sig)
        assert p.get_signal(sig.id) is sig

    def test_get_active_signals(self) -> None:
        from src.core.signals import SignalStatus

        p = InMemoryPersistence()
        active = make_signal()
        active_id = active.id
        # Create a draft signal (not active)
        draft = make_signal()
        # Modify status to DRAFT
        draft = type(active)(
            id=draft.id,
            entity_ref=draft.entity_ref,
            type=draft.type,
            claim=draft.claim + " extra",
            evidence_ids=draft.evidence_ids,
            direction=draft.direction,
            horizon=draft.horizon,
            score=draft.score,
            status=SignalStatus.DRAFT,
        )
        p.save_signal(active)
        p.save_signal(draft)
        active_signals = list(p.get_all_active_signals())
        assert len(active_signals) == 1
        assert active_signals[0].id == active_id


class TestResearchCRUD:
    def test_save_and_get(self) -> None:
        p = InMemoryPersistence()
        r = make_research()
        p.save_research(r)
        assert p.get_research(r.id) is r

    def test_get_research_for_entity(self) -> None:
        p = InMemoryPersistence()
        r = make_research()
        p.save_research(r)
        result = list(p.get_research_for_entity(r.entity_ref.id))
        assert r in result


class TestThesisCRUD:
    def test_save_and_get(self) -> None:
        p = InMemoryPersistence()
        t = make_thesis()
        p.save_thesis(t)
        assert p.get_thesis(t.id) is t

    def test_get_thesis_for_entity(self) -> None:
        p = InMemoryPersistence()
        t = make_thesis()
        p.save_thesis(t)
        result = p.get_thesis_for_entity(t.entity_ref.id)
        assert result is t

    def test_thesis_replacement(self) -> None:
        p = InMemoryPersistence()
        t1 = make_thesis()
        p.save_thesis(t1)
        # Evolve the thesis (creates new instance, same ID)
        t2 = t1.evolve(
            new_interpretation="Updated interpretation based on new data.",
            contributing_research_ids=("r1",),
            by="r1",
        )
        p.save_thesis(t2)
        retrieved = p.get_thesis(t1.id)
        # Retrieved is the most recent version
        assert retrieved.interpretation == t2.interpretation


class TestOverrideRecord:
    def test_append_only(self) -> None:
        p = InMemoryPersistence()
        # Add 3 records
        for i in range(3):
            p.save_override_record({"id": f"rec-{i}", "action": "adjust_score"})
        # Cannot delete or modify in place; only append
        # INV-11: append-only semantics
        assert len(p._override_records) == 3  # type: ignore[attr-defined]


class TestCheckpoint:
    def test_checkpoint_and_restore(self) -> None:
        p = InMemoryPersistence()
        source = make_source()
        entity = make_entity()
        p.save_source(source)
        p.save_entity(entity)

        # Checkpoint
        cycle_id = new_id()
        p.checkpoint(cycle_id)

        # Modify
        source2 = make_source()
        p.save_source(source2)
        assert p.get_source(source2.id) is source2

        # Restore
        assert p.restore(cycle_id) is True
        # After restore, source2 should be gone
        assert p.get_source(source2.id) is None

    def test_restore_nonexistent_checkpoint_fails(self) -> None:
        p = InMemoryPersistence()
        assert p.restore(new_id()) is False