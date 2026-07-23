"""Tests for PerEntityBriefBuilder (Phase 6 Checkpoint 3)."""

import pytest

from src.core.entities import Entity, EntityKind
from src.core.evidence import Evidence, Quality
from src.core.ids import ID
from src.core.invariants import Score
from src.core.lifecycle import ResearchStatus, ThesisStatus
from src.core.research import Research
from src.core.signals import EntityRef, Signal, SignalDirection, SignalHorizon, SignalStatus
from src.core.theses import Thesis, ThesisEvolution
from src.reports.builder import PerEntityBriefBuilder, PerEntityBriefInputs
from src.reports.models import ReportKind


# ----------------------- helpers -----------------------


def _entity(name: str = "ACME", entity_id: str = "e-1") -> Entity:
    return Entity.create(kind=EntityKind.COMPANY, name=name, id=ID(entity_id))


def _score(value: float) -> Score:
    return Score(value, value, value, value, value)


def _signal(
    composite: float,
    entity_id: str = "e-1",
    signal_id: str = "s-1",
    evidence_ids: tuple[ID, ...] = (ID("ev-1"),),
) -> Signal:
    return Signal.create(
        entity_ref=EntityRef(id=entity_id, kind="company"),
        type="capital_action",
        claim=f"claim {signal_id}",
        evidence_ids=evidence_ids,
        direction=SignalDirection.BULLISH,
        horizon=SignalHorizon.SHORT,
        score=_score(composite),
        status=SignalStatus.ACTIVE,
        id=ID(signal_id),
    )


def _research(
    question: str,
    *,
    entity_id: str = "e-1",
    signal_ids: tuple[ID, ...] = (ID("s-default"),),
    research_id: str = "r-1",
    status: ResearchStatus = ResearchStatus.OPEN,
) -> Research:
    """Build a Research. signal_ids defaults to one placeholder Signal so the
    Research invariant (≥1 signal) is satisfied even when the caller doesn't
    care about the signal."""
    base = Research.create(
        entity_ref=EntityRef(id=entity_id, kind="company"),
        question=question,
        signal_ids=signal_ids,
        id=ID(research_id),
    )
    if status != ResearchStatus.OPEN:
        return base.transition(status)
    return base


def _thesis(
    interpretation: str,
    *,
    entity_id: str = "e-1",
    status: ThesisStatus = ThesisStatus.EMERGING,
    thesis_id: str = "t-1",
    open_questions: tuple[str, ...] = (),
    evolution_history: tuple[ThesisEvolution, ...] = (),
) -> Thesis:
    return Thesis.create(
        entity_ref=EntityRef(id=entity_id, kind="company"),
        interpretation=interpretation,
        id=ID(thesis_id),
    ).evolve(
        new_interpretation=interpretation,
        contributing_research_ids=(),
        by="test",
        rationale="seed",
    ) if not evolution_history else Thesis.create(
        entity_ref=EntityRef(id=entity_id, kind="company"),
        interpretation=interpretation,
        id=ID(thesis_id),
    )


def _evidence(content: str = "E", ev_id: str = "ev-1") -> Evidence:
    return Evidence.create(
        source_ids=(ID("src-1"),),
        content=content,
        quality=Quality(0.9, 0.9, 0.9),
        id=ID(ev_id),
    )


# ----------------------- minimal inputs -----------------------


class TestMinimalInputs:
    def test_builds_with_anchor_entity_only(self) -> None:
        report = PerEntityBriefBuilder().build(
            PerEntityBriefInputs(anchor_entity=_entity())
        )
        assert report.kind == ReportKind.PER_ENTITY_BRIEF
        # Entity Overview is mandatory.
        titles = [s.title for s in report.sections]
        assert "Entity Overview" in titles
        # No Thesis → Current Thesis section omitted.
        assert "Current Thesis" not in titles

    def test_title_includes_entity_name(self) -> None:
        report = PerEntityBriefBuilder().build(
            PerEntityBriefInputs(anchor_entity=_entity(name="XYZ Corp"))
        )
        assert "XYZ Corp" in report.title

    def test_anchor_entity_id_in_report(self) -> None:
        report = PerEntityBriefBuilder().build(
            PerEntityBriefInputs(anchor_entity=_entity(entity_id="e-xyz"))
        )
        assert report.anchor_entity_id == "e-xyz"

    def test_word_budget_is_5000(self) -> None:
        report = PerEntityBriefBuilder().build(
            PerEntityBriefInputs(anchor_entity=_entity())
        )
        assert report.word_budget == 5_000


# ----------------------- Entity Overview -----------------------


class TestEntityOverview:
    def test_includes_name_and_kind(self) -> None:
        report = PerEntityBriefBuilder().build(
            PerEntityBriefInputs(anchor_entity=_entity(name="ACME"))
        )
        overview = next(s for s in report.sections if s.title == "Entity Overview")
        assert "ACME" in overview.body
        assert "kind=company" in overview.body

    def test_includes_aliases_when_present(self) -> None:
        entity = Entity.create(
            kind=EntityKind.COMPANY,
            name="ACME",
            aliases=("AC", "A.C.M.E."),
            id=ID("e-1"),
        )
        report = PerEntityBriefBuilder().build(
            PerEntityBriefInputs(anchor_entity=entity)
        )
        overview = next(s for s in report.sections if s.title == "Entity Overview")
        assert "AC" in overview.body
        assert "A.C.M.E." in overview.body

    def test_no_thesis_explicitly_states_so(self) -> None:
        report = PerEntityBriefBuilder().build(
            PerEntityBriefInputs(anchor_entity=_entity())
        )
        overview = next(s for s in report.sections if s.title == "Entity Overview")
        assert "not yet formed" in overview.body.lower() or "none" in overview.body.lower()

    def test_with_thesis_status_shown(self) -> None:
        sig = _signal(0.7)
        research = _research("Q?", signal_ids=(sig.id,))
        thesis = Thesis.create(
            entity_ref=EntityRef(id="e-1", kind="company"),
            interpretation="ACME is a growth story",
        )
        report = PerEntityBriefBuilder().build(
            PerEntityBriefInputs(
                anchor_entity=_entity(),
                signals=(sig,),
                researches=(research,),
                theses=(thesis,),
            )
        )
        overview = next(s for s in report.sections if s.title == "Entity Overview")
        assert "emerging" in overview.body


# ----------------------- Current Thesis -----------------------


class TestCurrentThesis:
    def test_section_present_when_thesis_exists(self) -> None:
        thesis = Thesis.create(
            entity_ref=EntityRef(id="e-1", kind="company"),
            interpretation="ACME growth",
        )
        report = PerEntityBriefBuilder().build(
            PerEntityBriefInputs(anchor_entity=_entity(), theses=(thesis,))
        )
        assert any(s.title == "Current Thesis" for s in report.sections)

    def test_section_omitted_when_no_thesis(self) -> None:
        report = PerEntityBriefBuilder().build(
            PerEntityBriefInputs(anchor_entity=_entity())
        )
        assert not any(s.title == "Current Thesis" for s in report.sections)

    def test_includes_interpretation_and_citation(self) -> None:
        thesis = Thesis.create(
            entity_ref=EntityRef(id="e-1", kind="company"),
            interpretation="ACME is a growth story",
        )
        report = PerEntityBriefBuilder().build(
            PerEntityBriefInputs(anchor_entity=_entity(), theses=(thesis,))
        )
        ct = next(s for s in report.sections if s.title == "Current Thesis")
        assert "ACME is a growth story" in ct.body
        assert "[thesis:" in ct.body
        assert "[thesis:" in str(ct.citations)

    def test_picks_latest_non_terminal_thesis(self) -> None:
        # Two theses: old is EMERGING (no history); new is EVOLVING.
        # The builder must pick the EVOLVING one (its evolution timestamp
        # is later than the old one's created_at).
        old = Thesis.create(
            entity_ref=EntityRef(id="e-1", kind="company"),
            interpretation="old interpretation",
            id=ID("t-old"),
        )
        new = Thesis.create(
            entity_ref=EntityRef(id="e-1", kind="company"),
            interpretation="new interpretation",
            id=ID("t-new"),
        )
        # Force a deterministic ordering by sleeping/evolving. Evolving
        # `new` appends a ThesisEvolution; its `at` is set by now_utc()
        # which is later than the synchronous `old.created_at`.
        new_evolved = new.evolve(
            new_interpretation="new interpretation evolved",
            contributing_research_ids=(),
            by="test",
            rationale="r",
        )
        # Sanity check: new_evolved has a non-empty evolution_history.
        assert len(new_evolved.evolution_history) == 1
        report = PerEntityBriefBuilder().build(
            PerEntityBriefInputs(
                anchor_entity=_entity(),
                theses=(old, new_evolved),
            )
        )
        ct = next(s for s in report.sections if s.title == "Current Thesis")
        assert "evolved" in ct.body
        assert "old interpretation" not in ct.body

    def test_filters_theses_by_entity(self) -> None:
        other_entity_thesis = Thesis.create(
            entity_ref=EntityRef(id="e-other", kind="company"),
            interpretation="other entity",
        )
        own_thesis = Thesis.create(
            entity_ref=EntityRef(id="e-1", kind="company"),
            interpretation="own entity",
        )
        report = PerEntityBriefBuilder().build(
            PerEntityBriefInputs(
                anchor_entity=_entity(),
                theses=(other_entity_thesis, own_thesis),
            )
        )
        ct = next(s for s in report.sections if s.title == "Current Thesis")
        assert "own entity" in ct.body
        assert "other entity" not in ct.body


# ----------------------- Supporting Signals (thesis-centric) -----------------------


class TestSupportingSignals:
    def test_signals_supporting_thesis_selected(self) -> None:
        # Thesis evolved from research r-1, which aggregated signal s-1.
        sig_supporting = _signal(0.9, signal_id="s-1")
        sig_unrelated = _signal(0.5, signal_id="s-2")
        research = _research("Q?", signal_ids=(sig_supporting.id,), research_id="r-1")
        thesis = Thesis.create(
            entity_ref=EntityRef(id="e-1", kind="company"),
            interpretation="growth story",
            id=ID("t-1"),
        )
        # Evolve thesis with contributing research = r-1.
        evolved = thesis.evolve(
            new_interpretation="growth story evolved",
            contributing_research_ids=(research.id,),
            by="test",
            rationale="r",
        )
        report = PerEntityBriefBuilder().build(
            PerEntityBriefInputs(
                anchor_entity=_entity(),
                signals=(sig_supporting, sig_unrelated),
                researches=(research,),
                theses=(evolved,),
            )
        )
        assert any(s.title == "Supporting Signals" for s in report.sections)
        ss = next(s for s in report.sections if s.title == "Supporting Signals")
        assert "s-1" in ss.body
        assert "s-2" not in ss.body

    def test_omitted_when_no_signals(self) -> None:
        report = PerEntityBriefBuilder().build(
            PerEntityBriefInputs(anchor_entity=_entity())
        )
        assert not any(s.title == "Supporting Signals" for s in report.sections)

    def test_omitted_when_no_supporting_chain(self) -> None:
        """If Thesis exists but contributes no Signals, the chain is omitted
        cleanly per the spec's omission rules."""
        sig = _signal(0.9, signal_id="s-1")
        thesis = Thesis.create(
            entity_ref=EntityRef(id="e-1", kind="company"),
            interpretation="thesis",
        )
        report = PerEntityBriefBuilder().build(
            PerEntityBriefInputs(
                anchor_entity=_entity(),
                signals=(sig,),
                theses=(thesis,),
            )
        )
        # No contributing research → no Supporting Signals section.
        assert not any(s.title == "Supporting Signals" for s in report.sections)

    def test_no_thesis_means_no_supporting_signals_section(self) -> None:
        """No Thesis → Supporting Signals section omitted.

        Per spec §2.3, signals that don't support a Thesis MUST NOT appear
        here. With no Thesis, no signals qualify.
        """
        sig = _signal(0.7, signal_id="s-1")
        report = PerEntityBriefBuilder().build(
            PerEntityBriefInputs(
                anchor_entity=_entity(),
                signals=(sig,),
            )
        )
        assert not any(s.title == "Supporting Signals" for s in report.sections)

    def test_signals_sorted_by_composite_desc(self) -> None:
        """Signals are sorted by composite descending when they support a Thesis."""
        # Set up a Thesis whose evolution links to a Research that aggregates
        # three signals; verify they're listed in composite-descending order.
        sigs = (
            _signal(0.3, signal_id="s-low"),
            _signal(0.9, signal_id="s-high"),
            _signal(0.6, signal_id="s-mid"),
        )
        research = _research(
            "Q?", signal_ids=tuple(s.id for s in sigs), research_id="r-1"
        )
        thesis = Thesis.create(
            entity_ref=EntityRef(id="e-1", kind="company"),
            interpretation="thesis",
        )
        evolved = thesis.evolve(
            new_interpretation="thesis evolved",
            contributing_research_ids=(research.id,),
            by="test",
            rationale="r",
        )
        report = PerEntityBriefBuilder().build(
            PerEntityBriefInputs(
                anchor_entity=_entity(),
                signals=sigs,
                researches=(research,),
                theses=(evolved,),
            )
        )
        ss = next(s for s in report.sections if s.title == "Supporting Signals")
        body = ss.body.split("\n")
        assert "s-high" in body[0]
        assert "s-mid" in body[1]
        assert "s-low" in body[2]


# ----------------------- Supporting Evidence -----------------------


class TestSupportingEvidence:
    def _build_with_supporting_chain(self, sigs, research_id="r-1"):
        """Helper: build a Thesis whose evolution links to a Research."""
        research = _research(
            "Q?", signal_ids=tuple(s.id for s in sigs), research_id=research_id
        )
        thesis = Thesis.create(
            entity_ref=EntityRef(id="e-1", kind="company"),
            interpretation="thesis",
        )
        evolved = thesis.evolve(
            new_interpretation="thesis evolved",
            contributing_research_ids=(research.id,),
            by="test",
            rationale="r",
        )
        return research, evolved

    def test_evidence_for_supporting_signals(self) -> None:
        ev1 = _evidence("E1", ev_id="ev-1")
        ev2 = _evidence("E2", ev_id="ev-2")
        sig = _signal(0.7, signal_id="s-1", evidence_ids=(ev1.id, ev2.id))
        research, evolved = self._build_with_supporting_chain((sig,))
        report = PerEntityBriefBuilder().build(
            PerEntityBriefInputs(
                anchor_entity=_entity(),
                signals=(sig,),
                researches=(research,),
                theses=(evolved,),
                evidences=(ev1, ev2),
            )
        )
        assert any(s.title == "Supporting Evidence" for s in report.sections)
        se = next(s for s in report.sections if s.title == "Supporting Evidence")
        assert "E1" in se.body
        assert "E2" in se.body

    def test_omitted_when_no_supporting_signals(self) -> None:
        # No supporting chain → no Supporting Signals → no Supporting Evidence.
        report = PerEntityBriefBuilder().build(
            PerEntityBriefInputs(anchor_entity=_entity())
        )
        assert not any(s.title == "Supporting Evidence" for s in report.sections)

    def test_unrelated_evidence_excluded(self) -> None:
        ev_matching = _evidence("matching", ev_id="ev-1")
        ev_other = _evidence("unrelated", ev_id="ev-other")
        sig = _signal(0.7, signal_id="s-1", evidence_ids=(ev_matching.id,))
        research, evolved = self._build_with_supporting_chain((sig,))
        report = PerEntityBriefBuilder().build(
            PerEntityBriefInputs(
                anchor_entity=_entity(),
                signals=(sig,),
                researches=(research,),
                theses=(evolved,),
                evidences=(ev_matching, ev_other),
            )
        )
        se = next(s for s in report.sections if s.title == "Supporting Evidence")
        assert "matching" in se.body
        assert "unrelated" not in se.body

    def test_long_content_truncated(self) -> None:
        long_content = "x" * 500
        ev = _evidence(long_content, ev_id="ev-1")
        sig = _signal(0.7, signal_id="s-1", evidence_ids=(ev.id,))
        research, evolved = self._build_with_supporting_chain((sig,))
        report = PerEntityBriefBuilder().build(
            PerEntityBriefInputs(
                anchor_entity=_entity(),
                signals=(sig,),
                researches=(research,),
                theses=(evolved,),
                evidences=(ev,),
            )
        )
        se = next(s for s in report.sections if s.title == "Supporting Evidence")
        assert "..." in se.body


# ----------------------- Research Progress -----------------------


class TestResearchProgress:
    def test_research_for_anchor_entity_listed(self) -> None:
        r1 = _research("Q1?", research_id="r-1").start()
        r2 = _research("Q2?", research_id="r-2")
        report = PerEntityBriefBuilder().build(
            PerEntityBriefInputs(
                anchor_entity=_entity(),
                researches=(r1, r2),
            )
        )
        rp = next(s for s in report.sections if s.title == "Research Progress")
        assert "Q1?" in rp.body
        assert "Q2?" in rp.body

    def test_research_for_other_entity_excluded(self) -> None:
        r_own = _research("own?", research_id="r-1")
        r_other = _research(
            "other?", research_id="r-2", entity_id="e-other"
        )
        report = PerEntityBriefBuilder().build(
            PerEntityBriefInputs(
                anchor_entity=_entity(),
                researches=(r_own, r_other),
            )
        )
        rp = next(s for s in report.sections if s.title == "Research Progress")
        assert "own?" in rp.body
        assert "other?" not in rp.body

    def test_omitted_when_no_research(self) -> None:
        report = PerEntityBriefBuilder().build(
            PerEntityBriefInputs(anchor_entity=_entity())
        )
        assert not any(s.title == "Research Progress" for s in report.sections)


# ----------------------- Open Questions -----------------------


class TestOpenQuestions:
    def test_section_present_when_thesis_has_questions(self) -> None:
        # Add open questions via Thesis.hold_with_open_question.
        thesis = Thesis.create(
            entity_ref=EntityRef(id="e-1", kind="company"),
            interpretation="thesis",
        )
        thesis = thesis.hold_with_open_question("Need more evidence on Q2")
        report = PerEntityBriefBuilder().build(
            PerEntityBriefInputs(
                anchor_entity=_entity(),
                theses=(thesis,),
            )
        )
        assert any(s.title == "Open Questions" for s in report.sections)
        oq = next(s for s in report.sections if s.title == "Open Questions")
        assert "Need more evidence on Q2" in oq.body

    def test_omitted_when_no_questions(self) -> None:
        thesis = Thesis.create(
            entity_ref=EntityRef(id="e-1", kind="company"),
            interpretation="thesis",
        )
        report = PerEntityBriefBuilder().build(
            PerEntityBriefInputs(
                anchor_entity=_entity(),
                theses=(thesis,),
            )
        )
        assert not any(s.title == "Open Questions" for s in report.sections)

    def test_omitted_when_no_thesis(self) -> None:
        report = PerEntityBriefBuilder().build(
            PerEntityBriefInputs(anchor_entity=_entity())
        )
        assert not any(s.title == "Open Questions" for s in report.sections)


# ----------------------- Upcoming Catalysts -----------------------


class TestUpcomingCatalysts:
    def test_section_present_when_notes_provided(self) -> None:
        report = PerEntityBriefBuilder().build(
            PerEntityBriefInputs(
                anchor_entity=_entity(),
                catalyst_notes=("Earnings Aug 5", "FOMC Sep 18"),
            )
        )
        assert any(s.title == "Upcoming Catalysts" for s in report.sections)
        uc = next(s for s in report.sections if s.title == "Upcoming Catalysts")
        assert "Earnings Aug 5" in uc.body

    def test_omitted_when_no_notes(self) -> None:
        report = PerEntityBriefBuilder().build(
            PerEntityBriefInputs(anchor_entity=_entity())
        )
        assert not any(s.title == "Upcoming Catalysts" for s in report.sections)


# ----------------------- Section order -----------------------


class TestSectionOrder:
    def test_canonical_order(self) -> None:
        # Build a fully-populated report; verify section order.
        sig = _signal(0.8, signal_id="s-1", evidence_ids=(ID("ev-1"),))
        research = _research("Q?", signal_ids=(sig.id,), research_id="r-1")
        thesis = Thesis.create(
            entity_ref=EntityRef(id="e-1", kind="company"),
            interpretation="thesis",
        )
        evolved = thesis.evolve(
            new_interpretation="thesis evolved",
            contributing_research_ids=(research.id,),
            by="test",
            rationale="r",
        )
        q_thesis = evolved.hold_with_open_question("Need more data")
        ev = _evidence("content", ev_id="ev-1")
        report = PerEntityBriefBuilder().build(
            PerEntityBriefInputs(
                anchor_entity=_entity(),
                signals=(sig,),
                researches=(research,),
                theses=(q_thesis,),
                evidences=(ev,),
                catalyst_notes=("Catalyst X",),
            )
        )
        titles = [s.title for s in report.sections]
        # Required canonical order.
        assert titles.index("Entity Overview") < titles.index("Current Thesis")
        assert titles.index("Current Thesis") < titles.index("Supporting Signals")
        assert titles.index("Supporting Signals") < titles.index("Supporting Evidence")
        assert titles.index("Supporting Evidence") < titles.index("Research Progress")
        assert titles.index("Research Progress") < titles.index("Open Questions")
        assert titles.index("Open Questions") < titles.index("Upcoming Catalysts")


# ----------------------- determinism -----------------------


class TestDeterminism:
    def test_two_calls_identical(self) -> None:
        sig = _signal(0.7, signal_id="s-1")
        thesis = Thesis.create(
            entity_ref=EntityRef(id="e-1", kind="company"),
            interpretation="thesis",
        )
        inputs = PerEntityBriefInputs(
            anchor_entity=_entity(),
            signals=(sig,),
            theses=(thesis,),
        )
        r1 = PerEntityBriefBuilder().build(inputs)
        r2 = PerEntityBriefBuilder().build(inputs)
        assert r1 == r2

    def test_signal_order_irrelevant(self) -> None:
        sigs = (
            _signal(0.3, signal_id="s-a"),
            _signal(0.9, signal_id="s-b"),
        )
        r1 = PerEntityBriefBuilder().build(
            PerEntityBriefInputs(anchor_entity=_entity(), signals=sigs)
        )
        r2 = PerEntityBriefBuilder().build(
            PerEntityBriefInputs(anchor_entity=_entity(), signals=tuple(reversed(sigs)))
        )
        assert r1 == r2


# ----------------------- metadata -----------------------


class TestReportMetadata:
    def test_cycle_ids_propagated(self) -> None:
        report = PerEntityBriefBuilder().build(
            PerEntityBriefInputs(anchor_entity=_entity()),
            cycle_ids=("c-1", "c-2"),
        )
        assert report.cycle_ids == ("c-1", "c-2")

    def test_degrade_mode_propagated(self) -> None:
        report = PerEntityBriefBuilder().build(
            PerEntityBriefInputs(anchor_entity=_entity()),
            degrade_mode=True,
        )
        assert report.degrade_mode is True


# ----------------------- dep inversion -----------------------


class TestDepInversion:
    def test_per_entity_brief_does_not_import_runtime(self) -> None:
        """The PerEntityBriefBuilder class itself must not import runtime.

        The reports module imports runtime.cycle under TYPE_CHECKING for
        DailyBriefInputs (Checkpoint 1, approved). Per-Entity Brief must
        not use it.
        """
        import inspect
        import re

        from src.reports.builder import PerEntityBriefBuilder

        source = inspect.getsource(PerEntityBriefBuilder)
        import_re = re.compile(
            r"\b(?:src\.runtime|src\.workflow|src\.persistence|src\.scheduler)"
        )
        matches = import_re.findall(source)
        assert not matches, (
            f"PerEntityBriefBuilder references forbidden modules: {matches}"
        )

    def test_per_entity_brief_does_not_import_knowledge(self) -> None:
        """Per-Entity Brief is an Entity Snapshot, not a Knowledge Summary."""
        import inspect
        import re

        from src.reports.builder import PerEntityBriefBuilder

        source = inspect.getsource(PerEntityBriefBuilder)
        # Match Knowledge module references.
        assert "KnowledgeAccumulator" not in source
        assert "InMemoryKnowledge" not in source
        assert "knowledge" not in source.lower() or "knowledge" in (
            "research progress"  # section title, OK
            or source.lower().count("knowledge") == 0
        )