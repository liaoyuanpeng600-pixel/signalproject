"""Tests for the Entity type."""

import pytest

from src.core.entities import Entity, EntityKind, EntityStatus


class TestEntityCreate:
    def test_minimal_creation(self) -> None:
        entity = Entity.create(
            kind=EntityKind.COMPANY,
            name="ACME Corp",
        )
        assert entity.id  # Auto-generated, non-empty
        assert entity.kind == EntityKind.COMPANY
        assert entity.name == "ACME Corp"
        assert entity.status == EntityStatus.ACTIVE
        assert entity.aliases == ()
        assert entity.classification == {}

    def test_with_aliases(self) -> None:
        entity = Entity.create(
            kind=EntityKind.COMPANY,
            name="ACME Corp",
            aliases=("ACME", "A.C.M.E."),
        )
        assert "ACME" in entity.aliases

    def test_with_classification(self) -> None:
        entity = Entity.create(
            kind=EntityKind.COMPANY,
            name="ACME Corp",
            classification={"sector": "Technology", "country": "US"},
        )
        assert entity.classification["sector"] == "Technology"

    def test_unique_ids(self) -> None:
        e1 = Entity.create(kind=EntityKind.COMPANY, name="A")
        e2 = Entity.create(kind=EntityKind.COMPANY, name="A")
        assert e1.id != e2.id


class TestEntityImmutability:
    def test_cannot_modify_id(self) -> None:
        entity = Entity.create(kind=EntityKind.COMPANY, name="ACME")
        with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
            entity.id = "new_id"  # type: ignore[misc]

    def test_cannot_modify_name_directly(self) -> None:
        entity = Entity.create(kind=EntityKind.COMPANY, name="ACME")
        with pytest.raises(Exception):
            entity.name = "Other"  # type: ignore[misc]


class TestEntityRename:
    def test_rename_creates_new_instance(self) -> None:
        entity = Entity.create(kind=EntityKind.COMPANY, name="ACME Corp")
        renamed = entity.rename("ACME Holdings")
        assert renamed.name == "ACME Holdings"
        assert renamed.id == entity.id  # ID unchanged
        assert renamed.status == EntityStatus.RENAMED

    def test_rename_adds_old_name_to_aliases(self) -> None:
        entity = Entity.create(kind=EntityKind.COMPANY, name="ACME Corp")
        renamed = entity.rename("ACME Holdings")
        assert "ACME Corp" in renamed.aliases

    def test_rename_does_not_duplicate_alias(self) -> None:
        entity = Entity.create(
            kind=EntityKind.COMPANY,
            name="ACME Corp",
            aliases=("ACME Corp",),
        )
        renamed = entity.rename("ACME Holdings")
        alias_count = renamed.aliases.count("ACME Corp")
        assert alias_count == 1

    def test_rename_to_empty_fails(self) -> None:
        entity = Entity.create(kind=EntityKind.COMPANY, name="ACME")
        with pytest.raises(ValueError):
            entity.rename("")


class TestEntityReclassify:
    def test_reclassify_changes_classification(self) -> None:
        entity = Entity.create(
            kind=EntityKind.COMPANY,
            name="ACME",
            classification={"sector": "Tech"},
        )
        reclassified = entity.reclassify(classification={"sector": "Healthcare"})
        assert reclassified.classification["sector"] == "Healthcare"


class TestEntityRetire:
    def test_retire_inactive(self) -> None:
        entity = Entity.create(kind=EntityKind.COMPANY, name="ACME")
        retired = entity.retire(EntityStatus.INACTIVE)
        assert retired.status == EntityStatus.INACTIVE

    def test_retire_delisted(self) -> None:
        entity = Entity.create(kind=EntityKind.COMPANY, name="ACME")
        retired = entity.retire(EntityStatus.DELISTED)
        assert retired.status == EntityStatus.DELISTED

    def test_retire_acquired(self) -> None:
        entity = Entity.create(kind=EntityKind.COMPANY, name="ACME")
        retired = entity.retire(EntityStatus.ACQUIRED)
        assert retired.status == EntityStatus.ACQUIRED

    def test_retire_with_invalid_status_fails(self) -> None:
        entity = Entity.create(kind=EntityKind.COMPANY, name="ACME")
        with pytest.raises(ValueError):
            entity.retire(EntityStatus.ACTIVE)  # type: ignore[arg-type]


class TestEntityValidation:
    def test_empty_id_rejected(self) -> None:
        with pytest.raises(ValueError):
            Entity(id="", kind=EntityKind.COMPANY, name="ACME")

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ValueError):
            Entity(id="abc", kind=EntityKind.COMPANY, name="")
