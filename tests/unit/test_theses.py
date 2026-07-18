"""Tests for the Thesis type."""

import pytest

from src.core.lifecycle import LifecycleError
from src.core.signals import EntityRef
from src.core.theses import Thesis, ThesisEvolution, ThesisStatus


def make_thesis(status: ThesisStatus = ThesisStatus.EMERGING) -> Thesis:
    return Thesis.create(
        entity_ref=EntityRef(id="entity-1", kind="company"),
        interpretation="ACME is undervalued relative to peers.",
        status=status,
    )


class TestThesisCreate:
    def test_minimal_creation(self) -> None:
        thesis = make_thesis()
        assert thesis.id
        assert thesis.entity_ref.id == "entity-1"
        assert thesis.interpretation == "ACME is undervalued relative to peers."
        assert thesis.status == ThesisStatus.EMERGING
        assert thesis.evolution_history == ()
        assert thesis.open_questions == ()

    def test_with_supporting_research(self) -> None:
        thesis = make_thesis()
        t = thesis.add_supporting_research("research-1")
        assert "research-1" in t.supporting_research_ids


class TestThesisValidation:
    def test_empty_interpretation_rejected(self) -> None:
        with pytest.raises(ValueError):
            Thesis.create(
                entity_ref=EntityRef(id="e", kind="company"),
                interpretation="",
            )

    def test_too_long_interpretation_rejected(self) -> None:
        with pytest.raises(ValueError):
            Thesis.create(
                entity_ref=EntityRef(id="e", kind="company"),
                interpretation="x" * 2001,
            )


class TestThesisLifecycle:
    def test_emerging_to_evolving(self) -> None:
        t = make_thesis()
        e = t.evolve(
            new_interpretation="ACME somewhat undervalued.",
            contributing_research_ids=("research-1",),
            by="research-1",
        )
        assert e.status == ThesisStatus.EVOLVING
        assert e.interpretation == "ACME somewhat undervalued."
        assert len(e.evolution_history) == 1

    def test_evolving_to_mature(self) -> None:
        t = make_thesis(ThesisStatus.EVOLVING)
        m = t.mature()
        assert m.status == ThesisStatus.MATURE

    def test_mature_to_evolving_reopen(self) -> None:
        t = make_thesis(ThesisStatus.MATURE)
        e = t.evolve(
            new_interpretation="ACME fairly valued now.",
            contributing_research_ids=("research-2",),
            by="research-2",
        )
        assert e.status == ThesisStatus.EVOLVING

    def test_mature_to_supersede(self) -> None:
        t = make_thesis(ThesisStatus.MATURE)
        s = t.supersede()
        assert s.status == ThesisStatus.SUPERSEDED

    def test_retire(self) -> None:
        # Retire is only allowed from EVOLVING or MATURE (per THESIS_LIFECYCLE).
        t = make_thesis(ThesisStatus.EVOLVING)
        r = t.retire()
        assert r.status == ThesisStatus.RETIRED

    def test_invalid_transition(self) -> None:
        t = make_thesis(ThesisStatus.EMERGING)
        with pytest.raises(LifecycleError):
            t.mature()  # Must go through EVOLVING first


class TestThesisEvolveHistory:
    def test_evolve_appends_history(self) -> None:
        t = make_thesis()
        t1 = t.evolve("X1", ("r1",), "r1")
        t2 = t1.evolve("X2", ("r2",), "r2")
        assert len(t2.evolution_history) == 2
        assert t2.evolution_history[0].prior_interpretation == "ACME is undervalued relative to peers."
        assert t2.evolution_history[1].new_interpretation == "X2"

    def test_evolution_records_kind(self) -> None:
        t = make_thesis()
        t1 = t.evolve("X", ("r1",), "r1")
        assert t1.evolution_history[0].kind == "evolve"

    def test_evolution_records_timestamps(self) -> None:
        t = make_thesis()
        t1 = t.evolve("X", ("r1",), "r1")
        assert t1.evolution_history[0].at


class TestThesisSupersession:
    def test_supersede_with_creates_successor(self) -> None:
        t = make_thesis()
        successor = t.supersede_with(
            new_interpretation="ACME fairly valued.",
            by="research-2",
            prior_id=t.id,
        )
        assert successor.id != t.id
        assert successor.entity_ref == t.entity_ref
        assert len(successor.evolution_history) == 1
        assert successor.evolution_history[0].kind == "supersede"

    def test_self_supersede_marks_prior(self) -> None:
        t = make_thesis()
        s = t.supersede()
        assert s.status == ThesisStatus.SUPERSEDED


class TestThesisOpenQuestions:
    def test_hold_with_open_question(self) -> None:
        t = make_thesis()
        t1 = t.hold_with_open_question("Insufficient data on Q2 capacity.")
        assert "Insufficient data on Q2 capacity." in t1.open_questions


class TestThesisImmutability:
    def test_id_immutable(self) -> None:
        t = make_thesis()
        with pytest.raises(Exception):
            t.id = "new_id"  # type: ignore[misc]

    def test_evolution_history_immutable(self) -> None:
        t = make_thesis()
        with pytest.raises(Exception):
            t.evolution_history = ()  # type: ignore[misc]


class TestThesisEvolutionValidation:
    def test_invalid_kind(self) -> None:
        with pytest.raises(ValueError):
            ThesisEvolution(
                at="2026-07-18T00:00:00+00:00",
                by="r1",
                kind="invalid_kind",  # Not in allowed set
                prior_interpretation="x",
                new_interpretation="y",
            )
