"""Tests for the checkpoint module."""

import pytest

from src.core.entities import Entity, EntityKind
from src.core.evidence import Evidence, Quality
from src.core.ids import ID
from src.persistence.checkpoint import checkpoint, restore
from src.persistence.in_memory import InMemoryStore, PersistenceError


def _make_entity(name: str) -> Entity:
    return Entity.create(kind=EntityKind.COMPANY, name=name)


def _make_evidence() -> Evidence:
    return Evidence.create(
        source_ids=(ID("src-1"),),
        content="text",
        quality=Quality(0.9, 0.8, 0.95),
    )


class TestCheckpoint:
    def test_checkpoint_round_trip(self) -> None:
        store = InMemoryStore()
        entity = _make_entity("ACME")
        store.put_entity(entity)
        snap = checkpoint(store)
        # Clear and restore.
        store.clear()
        restore(store, snap)
        assert store.get_entity(str(entity.id)).name == "ACME"

    def test_checkpoint_independent_of_later_changes(self) -> None:
        store = InMemoryStore()
        entity = _make_entity("ACME")
        store.put_entity(entity)
        snap = checkpoint(store)
        # Mutate live store; snapshot must remain unchanged.
        store.put_entity(entity.rename("ACME Holdings"))
        assert snap["entities"][str(entity.id)]["name"] == "ACME"  # type: ignore[index]

    def test_restore_to_different_store(self) -> None:
        src = InMemoryStore()
        entity = _make_entity("ACME")
        evidence = _make_evidence()
        src.put_entity(entity)
        src.put_evidence(evidence)
        snap = checkpoint(src)

        dst = InMemoryStore()
        restore(dst, snap)
        assert dst.get_entity(str(entity.id)).name == "ACME"
        assert dst.get_evidence(str(evidence.id)).content == "text"

    def test_invalid_snapshot_raises(self) -> None:
        store = InMemoryStore()
        with pytest.raises(PersistenceError):
            restore(store, {"not_a_valid_snapshot": True})