"""
Entity type per Object Model §1.

An Entity is anything in the world that research understanding can attach
to. Entities are recognized (not invented) and retired (not deleted).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum

from src.core.ids import ID, new_id


class EntityKind(str, Enum):
    """The kind of an Entity."""

    COMPANY = "company"
    INDUSTRY = "industry"
    MACRO_VARIABLE = "macro_variable"
    SECTOR = "sector"


class EntityStatus(str, Enum):
    """Lifecycle status of an Entity.

    Entities are never deleted; they are retired.
    """

    ACTIVE = "active"
    DELISTED = "delisted"
    ACQUIRED = "acquired"
    RENAMED = "renamed"
    INACTIVE = "inactive"


@dataclass(frozen=True, slots=True)
class Entity:
    """An anchor for research understanding.

    The id is immutable (INV-2). Other fields can be updated via lifecycle
    methods, which return new instances via dataclasses.replace().
    """

    id: ID
    kind: EntityKind
    name: str
    aliases: tuple[str, ...] = ()
    status: EntityStatus = EntityStatus.ACTIVE
    classification: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("Entity.id is required")
        if not self.name:
            raise ValueError("Entity.name is required")

    def rename(self, new_name: str) -> "Entity":
        """Rename the Entity. Returns a new instance."""
        if not new_name:
            raise ValueError("Entity.name cannot be empty")
        new_aliases = self.aliases + ((self.name,)) if self.name not in self.aliases else self.aliases
        return replace(self, name=new_name, aliases=new_aliases, status=EntityStatus.RENAMED)

    def reclassify(self, **changes: object) -> "Entity":
        """Reclassify the Entity. Returns a new instance with updated fields."""
        return replace(self, **changes)

    def retire(self, reason: EntityStatus = EntityStatus.INACTIVE) -> "Entity":
        """Retire the Entity. Returns a new instance with the given status."""
        if reason not in {EntityStatus.INACTIVE, EntityStatus.DELISTED, EntityStatus.ACQUIRED}:
            raise ValueError(f"Invalid retirement status: {reason}")
        return replace(self, status=reason)

    @classmethod
    def create(
        cls,
        kind: EntityKind,
        name: str,
        id: ID | None = None,
        aliases: tuple[str, ...] = (),
        classification: dict[str, str] | None = None,
    ) -> "Entity":
        """Factory method to create a new Entity with auto-generated ID."""
        return cls(
            id=id if id is not None else new_id(),
            kind=kind,
            name=name,
            aliases=aliases,
            classification=classification or {},
        )
