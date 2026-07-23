"""
Research synthesis — Phase 5 Checkpoint 1.

`ResearchSynthesizer` aggregates ACTIVE Signals into Research investigations.

The synthesizer is the canonical Phase 4/5 bridge:
- Reads ACTIVE Signals from the abstract `Store` interface.
- For each entity, finds an OPEN/ONGOING Research it can attach to,
  or creates a new Research if none exists.
- Returns a `SynthesisReport` summarizing the synthesis outcome.

This module contains NO business rules about WHAT a Research investigates;
it is a generic grouper. Domain-specific synthesis logic (e.g., "group
Signals by signal.type and entity_ref") is configurable via the
`synthesis_key` callable on the synthesizer.

Dependency rules:
- Depends only on `core.types`, `persistence.store.Store`, and
  `persistence.lifecycle` helpers.
- Does NOT import runtime.* internals.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from src.core.entities import Entity
from src.core.ids import ID
from src.core.lifecycle import ResearchStatus
from src.core.research import Research
from src.core.signals import EntityRef, Signal, SignalStatus


@dataclass(frozen=True, slots=True)
class SynthesisReport:
    """Result of one synthesis pass.

    Fields:
        signals_seen: Total ACTIVE Signals observed.
        research_created: New Research objects produced.
        research_updated: Existing Research objects appended to.
        research_concluded: Research that was concluded (e.g., because
            no further Signals are expected and the research is mature).
        by_entity: Map of entity_id -> count of new+updated research.
    """

    signals_seen: int
    research_created: tuple[ID, ...]
    research_updated: tuple[ID, ...]
    research_concluded: tuple[ID, ...]
    by_entity: dict[str, int] = field(default_factory=dict)


# Default synthesis key: group by entity_ref.id. Domain deployments can
# supply a richer key (entity_id + signal_type, etc.) without modifying
# the synthesizer.
def default_synthesis_key(signal: Signal) -> tuple[str, ...]:
    """Default grouping key for synthesis: just the entity_ref.id."""
    return (str(signal.entity_ref.id),)


class ResearchSynthesizer:
    """Aggregates Signals into Research.

    The synthesizer does NOT mutate Signals. It only reads them from the
    Store and produces new/updated Research. Lifecycle transitions on
    Research (open -> ongoing -> concluded) are handled by the synthesizer
    via Research methods (`.start()`, `.conclude()`).
    """

    def __init__(
        self,
        *,
        synthesis_key: Callable[[Signal], tuple[str, ...]] | None = None,
    ) -> None:
        self._key = synthesis_key or default_synthesis_key

    def synthesize(
        self,
        *,
        signals: tuple[Signal, ...],
        existing_research: tuple[Research, ...],
    ) -> SynthesisReport:
        """Produce a SynthesisReport from the given inputs.

        Args:
            signals: Signals to consider (typically ACTIVE; the synthesizer
                does not filter — caller decides which Signals are eligible).
            existing_research: All currently-stored Research.

        Returns:
            A SynthesisReport. The actual new/updated Research is included
            in the report's created/updated ID tuples; callers persist via
            `persistence.lifecycle.conclude_research` / `Store.put_research`.
        """
        # Group signals by their synthesis key.
        groups: dict[tuple[str, ...], list[Signal]] = {}
        for sig in signals:
            groups.setdefault(self._key(sig), []).append(sig)

        # Index existing research by entity_id for fast lookup.
        existing_by_entity: dict[str, list[Research]] = {}
        for r in existing_research:
            if r.status in {ResearchStatus.OPEN, ResearchStatus.ONGOING}:
                existing_by_entity.setdefault(str(r.entity_ref.id), []).append(r)

        created_ids: list[ID] = []
        updated_ids: list[ID] = []
        concluded_ids: list[ID] = []
        by_entity: dict[str, int] = {}

        for key, group_signals in groups.items():
            entity_id_str = key[0]
            # Find an OPEN/ONGOING Research for this entity; if multiple
            # exist, attach to the most recent (last appended).
            candidates = existing_by_entity.get(entity_id_str, [])
            target: Research | None = None
            if candidates:
                # Most recent = the one with the largest opened_at string
                # (ISO8601 UTC is lexicographically sortable).
                target = max(candidates, key=lambda r: r.opened_at)

            if target is None:
                # Create a new Research (synthesizer does NOT persist it;
                # KnowledgeUpdater does).
                entity_ref = group_signals[0].entity_ref
                new_research = Research.create(
                    entity_ref=EntityRef(id=entity_ref.id, kind=entity_ref.kind),
                    question=f"Aggregated observations for entity {entity_ref.id}",
                    signal_ids=tuple(s.id for s in group_signals),
                )
                created_ids.append(new_research.id)
                by_entity[entity_id_str] = by_entity.get(entity_id_str, 0) + 1
            else:
                # Append signals to existing research.
                new_signal_ids = tuple(s.id for s in group_signals)
                target = target.add_signals(new_signal_ids)
                updated_ids.append(target.id)
                by_entity[entity_id_str] = by_entity.get(entity_id_str, 0) + 1

        return SynthesisReport(
            signals_seen=len(signals),
            research_created=tuple(created_ids),
            research_updated=tuple(updated_ids),
            research_concluded=tuple(concluded_ids),
            by_entity=by_entity,
        )


__all__ = [
    "ResearchSynthesizer",
    "SynthesisReport",
    "default_synthesis_key",
]