"""Tests for the persistence lifecycle helpers."""

import pytest

from src.core.entities import Entity, EntityKind, EntityStatus
from src.core.evidence import Evidence, Quality
from src.core.ids import ID
from src.core.lifecycle import LifecycleError
from src.core.signals import EntityRef, Signal, SignalDirection, SignalHorizon
from src.core.invariants import Score
from src.core.sources import Source, SourceType
from src.core.theses import Thesis, ThesisStatus
from src.persistence.in_memory import InMemoryStore
from src.persistence.lifecycle import (
    append_curator_override,
    conclude_research,
    retire_entity,
    retire_signal,
    retire_source,
    supersede_signal,
    supersede_thesis,
)
from src.persistence.override import OverrideAction


def _make_entity() -> Entity:
    return Entity.create(kind=EntityKind.COMPANY, name="ACME")


def _make_source() -> Source:
    return Source.create(
        type=SourceType.NEWS_ARTICLE,
        url="https://example.com/x",
        name="Example",
    )


def _make_evidence() -> Evidence:
    return Evidence.create(
        source_ids=(ID("src-1"),),
        content="text",
        quality=Quality(0.9, 0.8, 0.95),
    )


def _make_signal(entity: Entity) -> Signal:
    return Signal.create(
        entity_ref=EntityRef(id=entity.id, kind=entity.kind.value),
        type="capital_action",
        claim="ACME dividend up 10%",
        evidence_ids=(ID("ev-1"),),
        direction=SignalDirection.BULLISH,
        horizon=SignalHorizon.SHORT,
        score=Score(0.5, 0.5, 0.5, 0.5, 0.5),
    )


class TestRetireEntity:
    def test_retire_persists_new_status(self) -> None:
        store = InMemoryStore()
        entity = _make_entity()
        store.put_entity(entity)
        retired = retire_entity(store, entity, EntityStatus.INACTIVE)
        assert retired.status == EntityStatus.INACTIVE
        assert store.get_entity(str(entity.id)).status == EntityStatus.INACTIVE

    def test_retire_invalid_status_raises(self) -> None:
        store = InMemoryStore()
        entity = _make_entity()
        with pytest.raises(ValueError):
            retire_entity(store, entity, EntityStatus.ACTIVE)  # type: ignore[arg-type]


class TestRetireSource:
    def test_retire_source(self) -> None:
        store = InMemoryStore()
        source = _make_source()
        store.put_source(source)
        retired = retire_source(store, source)
        assert retired.status.value == "retired"
        assert store.get_source(str(source.id)).status.value == "retired"


class TestSignalTerminal:
    def test_decay_signal(self) -> None:
        store = InMemoryStore()
        entity = _make_entity()
        signal = _make_signal(entity).verify().activate()
        store.put_signal(signal)
        decayed = retire_signal(store, signal)
        assert decayed.status.value == "decayed"
        assert store.get_signal(str(signal.id)).status.value == "decayed"

    def test_supersede_signal(self) -> None:
        store = InMemoryStore()
        entity = _make_entity()
        signal = _make_signal(entity).verify().activate()
        store.put_signal(signal)
        superseded = supersede_signal(store, signal)
        assert superseded.status.value == "superseded"

    def test_decay_draft_signal_raises_lifecycle(self) -> None:
        store = InMemoryStore()
        entity = _make_entity()
        signal = _make_signal(entity)  # DRAFT
        with pytest.raises(LifecycleError):
            retire_signal(store, signal)


class TestSupersedeThesis:
    def test_supersession_pair_persisted(self) -> None:
        store = InMemoryStore()
        entity_ref = EntityRef(id=ID("e-1"), kind=EntityKind.COMPANY.value)
        prior = Thesis.create(
            entity_ref=entity_ref,
            interpretation="ACME is a growth story",
        )
        store.put_thesis(prior)

        successor = supersede_thesis(
            store,
            prior,
            new_interpretation="ACME is a value trap",
            by="research:r-1",
        )

        # Prior is marked superseded in store.
        assert store.get_thesis(str(prior.id)).status == ThesisStatus.SUPERSEDED
        # Successor is stored with a fresh ID and EMERGING status.
        assert store.get_thesis(str(successor.id)).status == ThesisStatus.EMERGING
        assert successor.id != prior.id
        # Evolution history records the supersession.
        assert len(successor.evolution_history) == 1
        assert successor.evolution_history[0].kind == "supersede"


class TestAppendOverride:
    def test_append_curator_override(self) -> None:
        store = InMemoryStore()
        record = append_curator_override(
            store,
            target_id="sig-1",
            action=OverrideAction.MARK_NOISE,
            rationale="Duplicate of sig-0",
            actor="curator:alice",
        )
        assert record.target_id == ID("sig-1")
        assert record.action == OverrideAction.MARK_NOISE
        assert store.list_overrides() == (record,)

    def test_append_with_payload(self) -> None:
        store = InMemoryStore()
        record = append_curator_override(
            store,
            target_id="sig-2",
            action=OverrideAction.OVERRIDE_SCORE,
            rationale="Manual adjustment",
            actor="curator:bob",
            payload={"new_composite": 0.4},
        )
        assert record.payload == {"new_composite": 0.4}


class TestConcludeResearch:
    def test_conclude_persists(self) -> None:
        from src.core.research import Research

        store = InMemoryStore()
        research = Research.create(
            entity_ref=EntityRef(id=ID("e-1"), kind=EntityKind.COMPANY.value),
            question="Is ACME overvalued?",
            signal_ids=(ID("s-1"),),
        )
        store.put_research(research)
        concluded = conclude_research(store, research)
        assert concluded.status.value == "concluded"
        assert store.get_research(str(research.id)).status.value == "concluded"