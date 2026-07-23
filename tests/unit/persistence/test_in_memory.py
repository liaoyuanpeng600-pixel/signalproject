"""Tests for the InMemoryStore backend."""

import pytest

from src.core.entities import Entity, EntityKind
from src.core.evidence import Evidence, Quality
from src.core.invariants import Score
from src.core.ids import ID
from src.core.lifecycle import SignalStatus
from src.core.signals import EntityRef, Signal, SignalDirection, SignalHorizon
from src.core.sources import Source, SourceType
from src.persistence.in_memory import EvidenceAlreadyExists, InMemoryStore, PersistenceError
from src.persistence.override import OverrideAction, OverrideRecord


# ----------------------- helpers -----------------------


def _make_score() -> Score:
    return Score(magnitude=0.5, confidence=0.5, timeliness=0.5, novelty=0.5, actionability=0.5)


def _make_entity(name: str = "ACME") -> Entity:
    return Entity.create(kind=EntityKind.COMPANY, name=name)


def _make_source() -> Source:
    return Source.create(
        type=SourceType.NEWS_ARTICLE,
        url="https://example.com/news/1",
        name="Example News",
    )


def _make_evidence() -> Evidence:
    return Evidence.create(
        source_ids=(ID("src-1"),),
        content="ACME announced a 10% dividend increase.",
        quality=Quality(
            source_reliability=0.9, content_completeness=0.8, retrieval_confidence=0.95
        ),
    )


def _make_signal(entity: Entity, evidence: Evidence) -> Signal:
    return Signal.create(
        entity_ref=EntityRef(id=entity.id, kind=entity.kind.value),
        type="capital_action",
        claim="ACME announced a 10% dividend increase.",
        evidence_ids=(evidence.id,),
        direction=SignalDirection.BULLISH,
        horizon=SignalHorizon.SHORT,
        score=_make_score(),
    )


# ----------------------- basic CRUD -----------------------


class TestEntityCRUD:
    def test_put_and_get(self) -> None:
        store = InMemoryStore()
        entity = _make_entity()
        store.put_entity(entity)
        assert store.get_entity(str(entity.id)) == entity

    def test_get_missing_returns_none(self) -> None:
        store = InMemoryStore()
        assert store.get_entity("nonexistent") is None

    def test_put_replaces_existing(self) -> None:
        store = InMemoryStore()
        entity = _make_entity("ACME")
        store.put_entity(entity)
        renamed = entity.rename("ACME Holdings")
        store.put_entity(renamed)
        assert store.get_entity(str(entity.id)).name == "ACME Holdings"
        assert store.get_entity(str(entity.id)).status.value == "renamed"

    def test_list_entities(self) -> None:
        store = InMemoryStore()
        store.put_entity(_make_entity("A"))
        store.put_entity(_make_entity("B"))
        assert len(store.list_entities()) == 2


class TestSourceCRUD:
    def test_put_and_get(self) -> None:
        store = InMemoryStore()
        source = _make_source()
        store.put_source(source)
        assert store.get_source(str(source.id)) == source

    def test_deactivate_via_replacement(self) -> None:
        store = InMemoryStore()
        source = _make_source()
        store.put_source(source)
        store.put_source(source.deactivate())
        assert store.get_source(str(source.id)).status.value == "deactivated"


# ----------------------- Evidence immutability -----------------------


class TestEvidenceImmutability:
    def test_put_and_get(self) -> None:
        store = InMemoryStore()
        e = _make_evidence()
        store.put_evidence(e)
        assert store.get_evidence(str(e.id)) == e

    def test_overwrite_raises(self) -> None:
        store = InMemoryStore()
        e = _make_evidence()
        store.put_evidence(e)
        with pytest.raises(EvidenceAlreadyExists):
            store.put_evidence(e)  # same id -> overwrite rejected

    def test_mark_non_retrievable_creates_new_object_with_same_id(self) -> None:
        # `mark_non_retrievable` produces a logically new Evidence instance via
        # dataclass.replace(), but it preserves the original ID. Because the
        # store is write-once, attempting to overwrite an existing Evidence
        # raises EvidenceAlreadyExists. This documents the boundary between
        # in-memory mutation (via frozen dataclass.replace) and durable
        # persistence: once persisted, Evidence cannot be updated in-place.
        store = InMemoryStore()
        e = _make_evidence()
        store.put_evidence(e)
        new_e = e.mark_non_retrievable()
        # Sanity: it is a new object instance with retrievable=False.
        assert new_e is not e
        assert new_e.retrievable is False
        # But the ID is the same, so re-putting would conflict with immutability.
        with pytest.raises(EvidenceAlreadyExists):
            store.put_evidence(new_e)


# ----------------------- Signal CRUD -----------------------


class TestSignalCRUD:
    def test_put_and_get(self) -> None:
        store = InMemoryStore()
        entity = _make_entity()
        evidence = _make_evidence()
        signal = _make_signal(entity, evidence)
        store.put_signal(signal)
        assert store.get_signal(str(signal.id)) == signal

    def test_status_transition_persists(self) -> None:
        store = InMemoryStore()
        entity = _make_entity()
        evidence = _make_evidence()
        signal = _make_signal(entity, evidence)
        store.put_signal(signal)
        activated = signal.verify().activate()
        store.put_signal(activated)
        assert store.get_signal(str(signal.id)).status == SignalStatus.ACTIVE


# ----------------------- OverrideRecord append-only -----------------------


class TestOverrideRecordAppendOnly:
    def test_append_and_list(self) -> None:
        store = InMemoryStore()
        rec = OverrideRecord.create(
            target_id=ID("t-1"),
            action=OverrideAction.MARK_NOISE,
            rationale="Duplicate signal",
            actor="curator:alice",
        )
        store.append_override(rec)
        assert store.list_overrides() == (rec,)

    def test_list_filters_by_target(self) -> None:
        store = InMemoryStore()
        rec1 = OverrideRecord.create(
            target_id=ID("t-1"),
            action=OverrideAction.MARK_NOISE,
            rationale="dup",
            actor="curator:alice",
        )
        rec2 = OverrideRecord.create(
            target_id=ID("t-2"),
            action=OverrideAction.MARK_NOISE,
            rationale="dup",
            actor="curator:bob",
        )
        store.append_override(rec1)
        store.append_override(rec2)
        assert store.list_overrides(target_id="t-1") == (rec1,)
        assert store.list_overrides(target_id="t-2") == (rec2,)
        assert len(store.list_overrides()) == 2

    def test_records_are_immutable(self) -> None:
        store = InMemoryStore()
        rec = OverrideRecord.create(
            target_id=ID("t-1"),
            action=OverrideAction.MARK_NOISE,
            rationale="r",
            actor="a",
        )
        store.append_override(rec)
        # No public API to remove or modify; list_overrides returns a tuple
        # (not the underlying list), so the caller cannot mutate the log.
        listing = store.list_overrides()
        with pytest.raises((AttributeError, TypeError)):
            listing[0] = "replaced"  # type: ignore[index]


# ----------------------- Bulk operations -----------------------


class TestBulkOps:
    def test_clear_empties_store(self) -> None:
        store = InMemoryStore()
        store.put_entity(_make_entity())
        store.put_source(_make_source())
        store.put_evidence(_make_evidence())
        store.clear()
        assert store.list_entities() == ()
        assert store.list_sources() == ()
        assert store.list_evidence() == ()
        assert store.list_signals() == ()
        assert store.list_overrides() == ()

    def test_snapshot_is_independent_copy(self) -> None:
        store = InMemoryStore()
        entity = _make_entity("ACME")
        store.put_entity(entity)
        snap = store.snapshot()
        # Mutate the store; snapshot should not change.
        store.put_entity(entity.rename("ACME New"))
        assert snap["entities"][str(entity.id)]["name"] == "ACME"  # type: ignore[index]

    def test_snapshot_json_serializable(self) -> None:
        import json

        store = InMemoryStore()
        entity = _make_entity()
        evidence = _make_evidence()
        signal = _make_signal(entity, evidence)
        store.put_entity(entity)
        store.put_evidence(evidence)
        store.put_signal(signal)
        snap = store.snapshot()
        # Should round-trip through json.
        json.dumps(snap)

    def test_restore_replaces_contents(self) -> None:
        store = InMemoryStore()
        entity = _make_entity("ACME")
        evidence = _make_evidence()
        signal = _make_signal(entity, evidence)
        store.put_entity(entity)
        store.put_evidence(evidence)
        store.put_signal(signal)
        snap = store.snapshot()

        store.clear()
        assert store.list_entities() == ()

        store.restore(snap)
        assert store.get_entity(str(entity.id)).name == "ACME"
        assert store.get_signal(str(signal.id)).claim == signal.claim
        assert store.get_evidence(str(evidence.id)).content == evidence.content

    def test_invalid_snapshot_raises(self) -> None:
        store = InMemoryStore()
        with pytest.raises(PersistenceError):
            store.restore({"bogus": "shape"})


# ----------------------- Evidence-then-Signal dependency -----------------------


class TestPipelinePersistence:
    """End-to-end persistence flow: Entity → Source → Evidence → Signal."""

    def test_full_object_chain_persists(self) -> None:
        store = InMemoryStore()
        entity = _make_entity()
        source = _make_source()
        evidence = Evidence.create(
            source_ids=(source.id,),
            content="Filing text",
            quality=Quality(0.9, 0.8, 0.95),
        )
        signal = _make_signal(entity, evidence)

        store.put_entity(entity)
        store.put_source(source)
        store.put_evidence(evidence)
        store.put_signal(signal)

        # All retrievable, IDs match what we stored.
        assert store.get_entity(str(entity.id)) == entity
        assert store.get_source(str(source.id)) == source
        assert store.get_evidence(str(evidence.id)) == evidence
        assert store.get_signal(str(signal.id)) == signal

    def test_snapshot_restore_round_trip(self) -> None:
        store = InMemoryStore()
        entity = _make_entity()
        source = _make_source()
        evidence = _make_evidence()
        signal = _make_signal(entity, evidence)

        store.put_entity(entity)
        store.put_source(source)
        store.put_evidence(evidence)
        store.put_signal(signal)

        snap = store.snapshot()

        # New store; restore from snapshot.
        store2 = InMemoryStore()
        store2.restore(snap)

        assert store2.get_entity(str(entity.id)).name == entity.name
        assert store2.get_source(str(source.id)).url == source.url
        assert store2.get_evidence(str(evidence.id)).content == evidence.content
        assert store2.get_signal(str(signal.id)).claim == signal.claim