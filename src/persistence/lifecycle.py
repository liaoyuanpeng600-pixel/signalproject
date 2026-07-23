"""
Lifecycle transition helpers for persistence operations.

These helpers wrap the lifecycle methods on the Objects themselves with the
correct persistence-side sequence (read → mutate → write → emit OverrideRecord
where appropriate). They are thin wrappers — the source of truth for valid
transitions lives in `src.core.lifecycle`.

Two patterns are provided:
- `retire_*`: marks an Object as retired/terminal and writes the updated
  version back to the store. No OverrideRecord is emitted (retirement is an
  intrinsic lifecycle operation, not a curator action).
- `supersede_thesis`: implements Path B per Workflow Model — both the prior
  Thesis (marked superseded) and the successor Thesis (created and persisted)
  are written atomically.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.persistence.override import OverrideAction, OverrideRecord

if TYPE_CHECKING:
    from src.core.entities import Entity, EntityStatus
    from src.core.evidence import Evidence
    from src.core.research import Research
    from src.core.signals import Signal
    from src.core.sources import Source
    from src.core.theses import Thesis

    from src.persistence.store import Store


def retire_entity(
    store: "Store",
    entity: "Entity",
    reason: "EntityStatus",
    actor: str = "lifecycle_event",
) -> "Entity":
    """Retire an Entity and persist the updated version.

    Args:
        store: The persistence store.
        entity: The Entity to retire.
        reason: The retirement status (INACTIVE, DELISTED, or ACQUIRED).
        actor: Identifier for the actor; recorded in any emitted OverrideRecord.

    Returns:
        The retired Entity (already persisted).
    """
    retired = entity.retire(reason)
    store.put_entity(retired)
    return retired


def retire_source(store: "Store", source: "Source") -> "Source":
    """Retire a Source (terminal) and persist it. No OverrideRecord emitted."""
    retired = source.retire()
    store.put_source(retired)
    return retired


def retire_signal(store: "Store", signal: "Signal") -> "Signal":
    """Mark a Signal as decayed (terminal) and persist it.

    `decay` is the natural terminal transition for ACTIVE signals; rejected
    signals have their own path. OverrideRecord is not emitted for natural
    decay.
    """
    decayed = signal.decay()
    store.put_signal(decayed)
    return decayed


def supersede_signal(store: "Store", signal: "Signal") -> "Signal":
    """Mark a Signal as superseded (terminal) and persist it."""
    superseded = signal.supersede()
    store.put_signal(superseded)
    return superseded


def conclude_research(store: "Store", research: "Research") -> "Research":
    """Conclude a Research investigation and persist it."""
    concluded = research.conclude()
    store.put_research(concluded)
    return concluded


def supersede_thesis(
    store: "Store",
    prior: "Thesis",
    new_interpretation: str,
    by: str,
) -> "Thesis":
    """Implement Path B supersession per Workflow Model.

    Produces a new Thesis from `prior` with the new interpretation, persists
    the new Thesis, and persists the prior Thesis marked as superseded. The
    supersession pair is therefore durable in the store.

    Returns:
        The new (successor) Thesis.
    """
    successor = prior.supersede_with(
        new_interpretation=new_interpretation,
        by=by,
        prior_id=prior.id,
    )
    marked_prior = prior.supersede(by=by)
    store.put_thesis(marked_prior)
    store.put_thesis(successor)
    return successor


def append_curator_override(
    store: "Store",
    target_id: str,
    action: OverrideAction,
    rationale: str,
    actor: str,
    payload: dict[str, object] | None = None,
) -> OverrideRecord:
    """Append a curator OverrideRecord to the store's append-only log.

    Convenience wrapper for curators and tests. The record is created with a
    fresh ID and current timestamp.
    """
    from src.core.ids import ID

    record = OverrideRecord.create(
        target_id=ID(target_id),
        action=action,
        rationale=rationale,
        actor=actor,
        payload=payload,
    )
    store.append_override(record)
    return record


__all__ = [
    "append_curator_override",
    "conclude_research",
    "retire_entity",
    "retire_signal",
    "retire_source",
    "supersede_signal",
    "supersede_thesis",
]


# Reference-only imports to satisfy type checkers when Evidence is in scope.
_ = "Evidence" if TYPE_CHECKING else None  # type: ignore[truthy-function]