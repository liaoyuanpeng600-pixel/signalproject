"""Tests for ThemeEvolver (Phase 5 Checkpoint 1)."""

import pytest

from src.core.ids import ID
from src.core.research import Reasoning, Research, ResearchStatus
from src.core.signals import EntityRef, SignalDirection, SignalHorizon
from src.core.theses import Thesis, ThesisStatus
from src.research.themes import (
    ThemeEvolutionReport,
    ThemeEvolver,
    ThemePath,
    ThesisDelta,
    default_path_selector,
)


def _reasoning(significance: float) -> Reasoning:
    return Reasoning(
        significance=significance,
        causality=(),
        one_liner="",
    )


def _research(*, significance: float = 0.5, entity_id: str = "e-1") -> Research:
    return Research.create(
        entity_ref=EntityRef(id=entity_id, kind="company"),
        question="Q?",
        signal_ids=(ID("s-1"),),
        reasoning=_reasoning(significance),
    )


def _thesis(*, entity_id: str = "e-1", interpretation: str = "old interpretation") -> Thesis:
    return Thesis.create(
        entity_ref=EntityRef(id=entity_id, kind="company"),
        interpretation=interpretation,
    )


# ----------------------- defaults -----------------------


class TestThemeEvolverDefaults:
    def test_default_thresholds(self) -> None:
        e = ThemeEvolver()
        assert e.evolve_threshold == 0.55
        assert e.supersede_threshold == 0.85

    def test_invalid_thresholds(self) -> None:
        with pytest.raises(ValueError):
            ThemeEvolver(evolve_threshold=-0.1)
        with pytest.raises(ValueError):
            ThemeEvolver(supersede_threshold=1.5)
        with pytest.raises(ValueError):
            ThemeEvolver(evolve_threshold=0.9, supersede_threshold=0.5)


# ----------------------- path selection -----------------------


class TestPathSelection:
    def test_high_score_supersedes(self) -> None:
        path = default_path_selector(
            research=_research(significance=0.95),
            existing=_thesis(),
            evolve_threshold=0.55,
            supersede_threshold=0.85,
        )
        assert path == ThemePath.SUPERSEDE

    def test_mid_score_evolves(self) -> None:
        path = default_path_selector(
            research=_research(significance=0.7),
            existing=_thesis(),
            evolve_threshold=0.55,
            supersede_threshold=0.85,
        )
        assert path == ThemePath.EVOLVE

    def test_low_score_holds(self) -> None:
        path = default_path_selector(
            research=_research(significance=0.3),
            existing=_thesis(),
            evolve_threshold=0.55,
            supersede_threshold=0.85,
        )
        assert path == ThemePath.HOLD

    def test_no_research_holds(self) -> None:
        path = default_path_selector(
            research=None,
            existing=_thesis(),
            evolve_threshold=0.55,
            supersede_threshold=0.85,
        )
        assert path == ThemePath.HOLD

    def test_no_existing_returns_none(self) -> None:
        path = default_path_selector(
            research=_research(),
            existing=None,
            evolve_threshold=0.55,
            supersede_threshold=0.85,
        )
        assert path == ThemePath.NONE

    def test_no_reasoning_defaults_to_hold(self) -> None:
        # Research with no reasoning falls back to 0.5 significance, which
        # is below the default 0.55 evolve_threshold → HOLD (conservative).
        research = Research.create(
            entity_ref=EntityRef(id="e-1", kind="company"),
            question="Q?",
            signal_ids=(ID("s-1"),),
            # no reasoning
        )
        path = default_path_selector(
            research=research,
            existing=_thesis(),
            evolve_threshold=0.55,
            supersede_threshold=0.85,
        )
        assert path == ThemePath.HOLD


# ----------------------- Path A (EVOLVE) -----------------------


class TestPathEvolve:
    def test_evolve_appends_history(self) -> None:
        e = ThemeEvolver(evolve_threshold=0.5, supersede_threshold=0.9)
        t = _thesis()
        delta = e.evolve(research=_research(significance=0.7), existing_thesis=t)
        assert delta.path == ThemePath.EVOLVE
        assert delta.evolved_thesis is not None
        assert delta.evolved_thesis.id == t.id
        assert delta.evolved_thesis.status == ThesisStatus.EVOLVING
        assert len(delta.evolved_thesis.evolution_history) == 1
        assert delta.evolved_thesis.evolution_history[0].kind == "evolve"

    def test_evolve_uses_force_path(self) -> None:
        e = ThemeEvolver(evolve_threshold=0.5, supersede_threshold=0.9)
        t = _thesis()
        delta = e.evolve(
            research=_research(significance=0.2),
            existing_thesis=t,
            force_path=ThemePath.EVOLVE,
        )
        assert delta.path == ThemePath.EVOLVE


# ----------------------- Path B (SUPERSEDE) -----------------------


class TestPathSupersede:
    def test_supersede_creates_successor(self) -> None:
        e = ThemeEvolver(evolve_threshold=0.5, supersede_threshold=0.85)
        t = _thesis()
        delta = e.evolve(research=_research(significance=0.95), existing_thesis=t)
        assert delta.path == ThemePath.SUPERSEDE
        assert delta.prior_thesis is not None
        assert delta.successor_thesis is not None
        assert delta.prior_thesis.id == t.id
        assert delta.successor_thesis.id != t.id
        assert delta.successor_thesis.status == ThesisStatus.EMERGING
        assert len(delta.successor_thesis.evolution_history) == 1
        assert delta.successor_thesis.evolution_history[0].kind == "supersede"


# ----------------------- Path C (HOLD) -----------------------


class TestPathHold:
    def test_hold_annotates_open_question(self) -> None:
        e = ThemeEvolver(evolve_threshold=0.7, supersede_threshold=0.95)
        t = _thesis()
        delta = e.evolve(
            research=_research(significance=0.3),
            existing_thesis=t,
            rationale="Need more evidence",
        )
        assert delta.path == ThemePath.HOLD
        assert delta.evolved_thesis is not None
        assert delta.evolved_thesis.id == t.id
        assert "Need more evidence" in delta.evolved_thesis.open_questions


# ----------------------- NONE / no existing -----------------------


class TestNoOp:
    def test_no_existing_thesis(self) -> None:
        e = ThemeEvolver()
        delta = e.evolve(research=_research(), existing_thesis=None)
        assert delta.path == ThemePath.NONE
        assert delta.evolved_thesis is None


# ----------------------- evolve_many -----------------------


class TestEvolveMany:
    def test_processes_multiple_pairs(self) -> None:
        e = ThemeEvolver(evolve_threshold=0.5, supersede_threshold=0.9)
        pairs = (
            (_research(significance=0.7, entity_id="e-1"), _thesis(entity_id="e-1")),
            (_research(significance=0.95, entity_id="e-2"), _thesis(entity_id="e-2")),
            (None, None),  # no existing
        )
        report = e.evolve_many(pairs=pairs)
        assert isinstance(report, ThemeEvolutionReport)
        assert report.evolved_count == 1
        assert report.superseded_count == 1
        assert report.held_count == 0
        assert report.by_entity == {"e-1": 1, "e-2": 1}


# ----------------------- dep inversion -----------------------


class TestThemeEvolverNoRuntimeDeps:
    def test_themes_module_does_not_import_runtime(self) -> None:
        import re

        import src.research.themes as mod

        source = mod.__file__ or ""
        with open(source, encoding="utf-8") as f:
            contents = f.read()
        # No imports from runtime.* internals.
        assert not re.search(r"^\s*from\s+src\.runtime", contents, re.MULTILINE), (
            f"themes.py must not import runtime: {source}"
        )
        # No imports of workflow gates (no business rules).
        assert "from src.workflow.gates" not in contents
        assert "from src.workflow.stages" not in contents