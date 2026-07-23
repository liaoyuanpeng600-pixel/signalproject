"""
Theme (Thesis) evolution — Phase 5 Checkpoint 1.

`ThemeEvolver` decides which Thesis(es) to evolve, supersede, or hold-with-
open-question based on the latest Research outcomes.

Per Workflow Model Rule 2 (Thesis Update Stage), there are three paths:

- Path A — EVOLVE: existing Thesis interpretation changes incrementally;
  a new ThesisEvolution is appended; status transitions EMERGING/MATURE →
  EVOLVING (or stays EVOLVING).
- Path B — SUPERSEDE: a new Thesis replaces the prior. The prior Thesis
  is marked SUPERSEDED (terminal); a new Thesis is created with the new
  interpretation. Caller is responsible for persisting the pair.
- Path C — HOLD: the existing Thesis is annotated with an open question;
  no evolution occurs.

Path selection is driven by:
1. Composite score of the latest Research (if attached).
2. Interpretation change magnitude (configurable).
3. Explicit operator hint via `force_path` parameter.

This module does NOT inspect gate IDs or workflow internals. It consumes
Research and Thesis objects only.

Dependency rules:
- Depends on `core.types` and `persistence.lifecycle` helpers.
- Does NOT import runtime.* internals.
- Does NOT import workflow gates.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum

from src.core.ids import ID
from src.core.research import Research
from src.core.theses import Thesis, ThesisEvolution, ThesisStatus
from src.core.timestamps import now_utc


class ThemePath(str, Enum):
    """The three thesis-update paths per Workflow Model Rule 2."""

    EVOLVE = "evolve"          # Path A
    SUPERSEDE = "supersede"    # Path B
    HOLD = "hold"              # Path C
    NONE = "none"              # No thesis change


@dataclass(frozen=True, slots=True)
class ThesisDelta:
    """A single theme-evolution outcome.

    For Path A (EVOLVE): `evolved_thesis` is the updated Thesis.
    For Path B (SUPERSEDE): `prior_thesis` is the superseded Thesis and
        `successor_thesis` is the new one.
    For Path C (HOLD): `evolved_thesis` is the held Thesis (with new
        open_question annotation).
    For NONE: all fields are None.
    """

    path: ThemePath
    rationale: str
    evolved_thesis: Thesis | None = None
    prior_thesis: Thesis | None = None
    successor_thesis: Thesis | None = None


@dataclass(frozen=True, slots=True)
class ThemeEvolutionReport:
    """Outcome of one theme evolution pass."""

    deltas: tuple[ThesisDelta, ...]
    by_entity: dict[str, int] = field(default_factory=dict)

    @property
    def evolved_count(self) -> int:
        return sum(1 for d in self.deltas if d.path == ThemePath.EVOLVE)

    @property
    def superseded_count(self) -> int:
        return sum(1 for d in self.deltas if d.path == ThemePath.SUPERSEDE)

    @property
    def held_count(self) -> int:
        return sum(1 for d in self.deltas if d.path == ThemePath.HOLD)


def default_path_selector(
    *,
    research: Research | None,
    existing: Thesis | None,
    evolve_threshold: float,
    supersede_threshold: float,
) -> ThemePath:
    """Default path selection logic.

    Args:
        research: The latest Research driving this evolution (may be None
            if no Research is available).
        existing: The current Thesis for this entity (may be None).
        evolve_threshold: Composite score above which Path A (EVOLVE) is chosen.
        supersede_threshold: Composite score above which Path B (SUPERSEDE)
            is chosen.

    Returns:
        The chosen ThemePath.
    """
    if existing is None:
        # No thesis to evolve; the synthesizer/updater creates one elsewhere.
        return ThemePath.NONE

    # If no research signal, default to HOLD (Path C) to be conservative.
    if research is None:
        return ThemePath.HOLD

    score = research.reasoning.significance if research.reasoning else 0.5

    if score >= supersede_threshold:
        return ThemePath.SUPERSEDE
    if score >= evolve_threshold:
        return ThemePath.EVOLVE
    return ThemePath.HOLD


class ThemeEvolver:
    """Decides and applies ThemePath decisions for each Research/Thesis pair.

    The evolver is stateless beyond its configuration (path_selector +
    thresholds). It does NOT persist Thesis changes; callers (KnowledgeUpdater)
    do that via `persistence.lifecycle.supersede_thesis` or direct store puts.
    """

    def __init__(
        self,
        *,
        evolve_threshold: float = 0.55,
        supersede_threshold: float = 0.85,
        path_selector: Callable[..., ThemePath] | None = None,
    ) -> None:
        if not (0.0 <= evolve_threshold <= 1.0):
            raise ValueError(f"evolve_threshold must be in [0.0, 1.0], got {evolve_threshold}")
        if not (0.0 <= supersede_threshold <= 1.0):
            raise ValueError(f"supersede_threshold must be in [0.0, 1.0], got {supersede_threshold}")
        if supersede_threshold < evolve_threshold:
            raise ValueError(
                f"supersede_threshold ({supersede_threshold}) must be >= "
                f"evolve_threshold ({evolve_threshold})"
            )
        self._evolve_threshold = evolve_threshold
        self._supersede_threshold = supersede_threshold
        self._path_selector = path_selector or default_path_selector

    @property
    def evolve_threshold(self) -> float:
        return self._evolve_threshold

    @property
    def supersede_threshold(self) -> float:
        return self._supersede_threshold

    def evolve(
        self,
        *,
        research: Research | None,
        existing_thesis: Thesis | None,
        force_path: ThemePath | None = None,
        rationale: str = "",
        by: str = "theme_evolver",
    ) -> ThesisDelta:
        """Decide and apply a theme evolution.

        Args:
            research: The latest Research driving this evolution.
            existing_thesis: The current Thesis (or None if none exists).
            force_path: If set, override the path selector.
            rationale: Human-readable explanation recorded in ThesisEvolution.
            by: Identifier for the actor; recorded in evolution history.

        Returns:
            A `ThesisDelta` describing the outcome.
        """
        path = (
            force_path
            if force_path is not None
            else self._path_selector(
                research=research,
                existing=existing_thesis,
                evolve_threshold=self._evolve_threshold,
                supersede_threshold=self._supersede_threshold,
            )
        )

        if path == ThemePath.NONE:
            return ThesisDelta(path=path, rationale="no thesis to evolve")

        if existing_thesis is None:
            return ThesisDelta(
                path=path,
                rationale="no existing thesis; synthesis should create one",
            )

        if path == ThemePath.EVOLVE:
            new_interpretation = self._compose_interpretation(
                existing_thesis, research
            )
            evolved = existing_thesis.evolve(
                new_interpretation=new_interpretation,
                contributing_research_ids=(research.id,) if research else (),
                by=by,
                rationale=rationale or "Path A: incremental evolution",
            )
            return ThesisDelta(
                path=path,
                rationale=rationale or "Path A: incremental evolution",
                evolved_thesis=evolved,
            )

        if path == ThemePath.SUPERSEDE:
            new_interpretation = self._compose_interpretation(existing_thesis, research)
            successor = existing_thesis.supersede_with(
                new_interpretation=new_interpretation,
                by=by,
                prior_id=existing_thesis.id,
            )
            return ThesisDelta(
                path=path,
                rationale=rationale or "Path B: thesis superseded",
                prior_thesis=existing_thesis,
                successor_thesis=successor,
            )

        if path == ThemePath.HOLD:
            open_q = (
                rationale
                or (research.question if research else "Insufficient evidence to evolve")
            )
            held = existing_thesis.hold_with_open_question(open_q)
            return ThesisDelta(
                path=path,
                rationale=rationale or "Path C: held with open question",
                evolved_thesis=held,
            )

        # Exhaustiveness: unknown path.
        return ThesisDelta(path=path, rationale=f"unhandled path: {path}")

    def evolve_many(
        self,
        *,
        pairs: tuple[tuple[Research | None, Thesis | None], ...],
        force_path: ThemePath | None = None,
        rationale: str = "",
        by: str = "theme_evolver",
    ) -> ThemeEvolutionReport:
        """Apply evolution to many (Research, Thesis) pairs.

        Returns a ThemeEvolutionReport aggregating all deltas.
        """
        deltas: list[ThesisDelta] = []
        by_entity: dict[str, int] = {}
        for research, thesis in pairs:
            delta = self.evolve(
                research=research,
                existing_thesis=thesis,
                force_path=force_path,
                rationale=rationale,
                by=by,
            )
            deltas.append(delta)
            # Track by entity if we have an associated Thesis or Research.
            entity_id = None
            if thesis is not None:
                entity_id = str(thesis.entity_ref.id)
            elif research is not None:
                entity_id = str(research.entity_ref.id)
            if entity_id is not None and delta.path != ThemePath.NONE:
                by_entity[entity_id] = by_entity.get(entity_id, 0) + 1
        return ThemeEvolutionReport(deltas=tuple(deltas), by_entity=by_entity)

    @staticmethod
    def _compose_interpretation(existing: Thesis, research: Research | None) -> str:
        """Compose the new interpretation string for Path A/B."""
        if research is None:
            return existing.interpretation
        return f"{existing.interpretation} [updated: {research.question}]"


__all__ = [
    "ThemeEvolver",
    "ThemeEvolutionReport",
    "ThemePath",
    "ThesisDelta",
    "default_path_selector",
]