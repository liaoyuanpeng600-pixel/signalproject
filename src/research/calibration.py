"""
Calibration data emission — Phase 5 Checkpoint 3.

This module aggregates curator activity and conflict events into a single
`CalibrationData` record per emission cycle. The emitted record is the
input for downstream calibration work (e.g., Brier-score analysis,
rubric adjustment, scoring-framework calibration in Phase 3 of the
implementation roadmap).

Emission captures:
- Signal score calibration: every `OVERRIDE_SCORE` action's
  (target_id, original_composite, new_composite) triple. This is the raw
  material for measuring scoring-model drift.
- Curator action distribution: counts per OverrideAction (8 buckets).
- Conflict distribution: counts per ConflictKind (3 buckets).
- Theme path distribution: counts per ThemePath (3 buckets).

Dependency rules:
- Calibration depends ONLY on `core.types`, `persistence.store.Store`,
  `persistence.override.OverrideRecord`, and `research.conflicts.ConflictEvent`.
- Calibration does NOT import runtime.* internals.
- Calibration does NOT import workflow gates.
- Calibration does NOT mutate the Store; emission is a pure read-side
  computation that produces a serializable record.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from src.core.ids import ID
from src.core.signals import Signal
from src.core.timestamps import now_utc
from src.persistence.override import OverrideAction, OverrideRecord
from src.research.conflicts import ConflictEvent, ConflictKind
from src.research.themes import ThemePath

if TYPE_CHECKING:
    from src.persistence.store import Store


@dataclass(frozen=True, slots=True)
class ScoreDelta:
    """A single curator-driven score override.

    Fields:
        target_id: The Signal whose score was overridden.
        original_composite: The composite score before override (or None
            if the Signal is no longer in the Store).
        new_composite: The replacement composite from the override payload.
    """

    target_id: ID
    original_composite: float | None
    new_composite: float


@dataclass(frozen=True, slots=True)
class CalibrationData:
    """One calibration emission record.

    Fields:
        cycle_id: Identifier of the cycle this emission covers (or any
            caller-supplied label).
        emitted_at: ISO8601 UTC timestamp.
        total_signals: Signals currently in the Store.
        total_overrides: OverrideRecords covered by this emission.
        total_conflicts: ConflictEvents covered by this emission.
        total_themes: Themes (Theses) currently in the Store.
        score_deltas: Per-override score calibration triples.
        override_action_counts: count per OverrideAction value.
        conflict_counts: count per ConflictKind value.
        theme_path_counts: count per ThemePath value.
    """

    cycle_id: str
    emitted_at: str
    total_signals: int
    total_overrides: int
    total_conflicts: int
    total_themes: int
    score_deltas: tuple[ScoreDelta, ...]
    override_action_counts: dict[str, int] = field(default_factory=dict)
    conflict_counts: dict[str, int] = field(default_factory=dict)
    theme_path_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable dict view of the record."""
        return {
            "cycle_id": self.cycle_id,
            "emitted_at": self.emitted_at,
            "total_signals": self.total_signals,
            "total_overrides": self.total_overrides,
            "total_conflicts": self.total_conflicts,
            "total_themes": self.total_themes,
            "score_deltas": [
                {
                    "target_id": str(d.target_id),
                    "original_composite": d.original_composite,
                    "new_composite": d.new_composite,
                }
                for d in self.score_deltas
            ],
            "override_action_counts": dict(self.override_action_counts),
            "conflict_counts": dict(self.conflict_counts),
            "theme_path_counts": dict(self.theme_path_counts),
        }

    def to_json(self) -> str:
        """Return the dict view serialized as JSON."""
        return json.dumps(self.to_dict(), sort_keys=True)


class CalibrationEmitter:
    """Aggregates calibration inputs into a single `CalibrationData`.

    Pure: the emitter does not mutate any input. It computes a snapshot
    over the supplied data and returns the result.
    """

    def emit(
        self,
        *,
        cycle_id: str,
        overrides: Iterable[OverrideRecord],
        conflicts: Iterable[ConflictEvent],
        theme_paths: Iterable[ThemePath],
        signals: Iterable[Signal] = (),
        themes: Iterable[object] = (),  # Thesis objects; typed loosely to avoid core.knowledge cycle
    ) -> CalibrationData:
        """Compute a CalibrationData snapshot.

        Args:
            cycle_id: Identifier for this emission (typically the cycle id).
            overrides: OverrideRecords to summarize. Pass `store.list_overrides()`
                or a filtered subset for a window.
            conflicts: ConflictEvents to summarize. Pass the output of
                `ConflictDetector.detect()`.
            theme_paths: ThemePath values produced by `ThemeEvolver` for this
                cycle.
            signals: All Signals currently in the Store (for total count and
                score-delta lookup).
            themes: All Theses currently in the Store (for total count).

        Returns:
            A `CalibrationData` snapshot.
        """
        signals_tuple = tuple(signals)
        themes_tuple = tuple(themes)
        overrides_tuple = tuple(overrides)
        conflicts_tuple = tuple(conflicts)
        theme_paths_tuple = tuple(theme_paths)

        # Build a quick lookup of original composite scores by Signal id.
        original_by_id: dict[str, float] = {
            str(s.id): s.score.composite for s in signals_tuple
        }

        # Score deltas: only OverrideAction.OVERRIDE_SCORE records.
        score_deltas: list[ScoreDelta] = []
        for r in overrides_tuple:
            if r.action != OverrideAction.OVERRIDE_SCORE:
                continue
            payload = r.payload or {}
            new_value = payload.get("new_composite")
            if not isinstance(new_value, (int, float)):
                # Malformed payload; skip with no recorded delta.
                continue
            score_deltas.append(
                ScoreDelta(
                    target_id=r.target_id,
                    original_composite=original_by_id.get(str(r.target_id)),
                    new_composite=float(new_value),
                )
            )

        # Override action distribution.
        action_counts = Counter(r.action.value for r in overrides_tuple)

        # Conflict distribution.
        conflict_counts = Counter(c.kind.value for c in conflicts_tuple)

        # Theme path distribution.
        theme_path_counts = Counter(p.value for p in theme_paths_tuple)

        return CalibrationData(
            cycle_id=cycle_id,
            emitted_at=now_utc(),
            total_signals=len(signals_tuple),
            total_overrides=len(overrides_tuple),
            total_conflicts=len(conflicts_tuple),
            total_themes=len(themes_tuple),
            score_deltas=tuple(score_deltas),
            override_action_counts=dict(action_counts),
            conflict_counts=dict(conflict_counts),
            theme_path_counts=dict(theme_path_counts),
        )

    def emit_from_store(
        self,
        *,
        cycle_id: str,
        store: "Store",
        conflicts: Iterable[ConflictEvent] = (),
        theme_paths: Iterable[ThemePath] = (),
    ) -> CalibrationData:
        """Convenience: emit using a Store as the source of truth.

        Reads signals, themes, and override records from the Store. The
        caller still supplies conflicts and theme paths (those are computed
        by other Research-layer components, not the Store).
        """
        return self.emit(
            cycle_id=cycle_id,
            overrides=store.list_overrides(),
            conflicts=conflicts,
            theme_paths=theme_paths,
            signals=store.list_signals(),
            themes=store.list_theses(),
        )


__all__ = [
    "CalibrationData",
    "CalibrationEmitter",
    "ScoreDelta",
]