"""Tests for WeeklyReviewBuilder (Phase 6 Checkpoint 2)."""

import pytest

from src.core.entities import Entity, EntityKind
from src.core.evidence import Evidence, Quality
from src.core.ids import ID
from src.core.invariants import Score
from src.core.lifecycle import ResearchStatus
from src.core.research import Research
from src.core.signals import EntityRef, Signal, SignalDirection, SignalHorizon, SignalStatus
from src.core.theses import Thesis
from src.reports.builder import WeeklyReviewBuilder, WeeklyReviewInputs
from src.reports.models import ReportKind


# ----------------------- helpers -----------------------


def _score(value: float) -> Score:
    return Score(value, value, value, value, value)


def _signal(composite: float, signal_id: str = "s-1") -> Signal:
    return Signal.create(
        entity_ref=EntityRef(id="e-1", kind="company"),
        type="capital_action",
        claim=f"claim {signal_id}",
        evidence_ids=(ID("ev-1"),),
        direction=SignalDirection.BULLISH,
        horizon=SignalHorizon.SHORT,
        score=_score(composite),
        status=SignalStatus.ACTIVE,
        id=ID(signal_id),
    )


def _research(question: str = "Q?") -> Research:
    return Research.create(
        entity_ref=EntityRef(id="e-1", kind="company"),
        question=question,
        signal_ids=(ID("s-1"),),
    )


def _thesis(interpretation: str = "growth story") -> Thesis:
    return Thesis.create(
        entity_ref=EntityRef(id="e-1", kind="company"),
        interpretation=interpretation,
    )


def _evidence(content: str = "E") -> Evidence:
    return Evidence.create(
        source_ids=(ID("src-1"),),
        content=content,
        quality=Quality(0.9, 0.9, 0.9),
    )


# ----------------------- empty / minimal inputs -----------------------


class TestMinimalInputs:
    def test_builds_with_period_only(self) -> None:
        report = WeeklyReviewBuilder().build(
            WeeklyReviewInputs(period_label="Week of 2026-07-13")
        )
        assert report.kind == ReportKind.WEEKLY_REVIEW
        # Only Executive Summary is mandatory; optional sections omitted.
        assert any(s.title == "Executive Summary" for s in report.sections)
        # No Major Signals section if no signals.
        assert not any(s.title == "Major Signals" for s in report.sections)

    def test_title_includes_period_label(self) -> None:
        report = WeeklyReviewBuilder().build(
            WeeklyReviewInputs(period_label="Week of 2026-07-13")
        )
        assert "Week of 2026-07-13" in report.title

    def test_word_budget_is_15k(self) -> None:
        report = WeeklyReviewBuilder().build(
            WeeklyReviewInputs(period_label="p")
        )
        assert report.word_budget == 15_000


# ----------------------- Executive Summary -----------------------


class TestExecutiveSummary:
    def test_counts_inputs(self) -> None:
        report = WeeklyReviewBuilder().build(
            WeeklyReviewInputs(
                period_label="p",
                signals=(_signal(0.7, "s-1"), _signal(0.8, "s-2")),
                researches=(_research("Q1?"), _research("Q2?")),
                theses=(_thesis(),),
            )
        )
        summary = next(s for s in report.sections if s.title == "Executive Summary")
        assert "2 Signals" in summary.body
        assert "2 Research updates" in summary.body
        assert "1 Thesis changes" in summary.body

    def test_period_label_included(self) -> None:
        report = WeeklyReviewBuilder().build(
            WeeklyReviewInputs(period_label="Week of 2026-07-13")
        )
        summary = next(s for s in report.sections if s.title == "Executive Summary")
        assert "Week of 2026-07-13" in summary.body


# ----------------------- Major Signals -----------------------


class TestMajorSignals:
    def test_top_signals_sorted_by_composite_desc(self) -> None:
        sigs = (
            _signal(0.3, "s-low"),
            _signal(0.9, "s-high"),
            _signal(0.6, "s-mid"),
        )
        report = WeeklyReviewBuilder().build(
            WeeklyReviewInputs(period_label="p", signals=sigs)
        )
        major = next(s for s in report.sections if s.title == "Major Signals")
        body_lines = major.body.split("\n")
        assert "s-high" in body_lines[0]
        assert "s-mid" in body_lines[1]
        assert "s-low" in body_lines[2]

    def test_top_signals_capped_at_10(self) -> None:
        sigs = tuple(_signal(0.5, f"s-{i}") for i in range(20))
        report = WeeklyReviewBuilder().build(
            WeeklyReviewInputs(period_label="p", signals=sigs)
        )
        major = next(s for s in report.sections if s.title == "Major Signals")
        numbered = [l for l in major.body.split("\n") if l and l[0].isdigit()]
        assert len(numbered) == 10

    def test_top_signals_stable_tiebreak_by_id(self) -> None:
        # Equal composite; lower id should sort first.
        sigs = (
            _signal(0.7, "s-z"),
            _signal(0.7, "s-a"),
            _signal(0.7, "s-m"),
        )
        report = WeeklyReviewBuilder().build(
            WeeklyReviewInputs(period_label="p", signals=sigs)
        )
        major = next(s for s in report.sections if s.title == "Major Signals")
        body_lines = major.body.split("\n")
        assert "s-a" in body_lines[0]
        assert "s-m" in body_lines[1]
        assert "s-z" in body_lines[2]

    def test_section_omitted_when_no_signals(self) -> None:
        report = WeeklyReviewBuilder().build(WeeklyReviewInputs(period_label="p"))
        assert not any(s.title == "Major Signals" for s in report.sections)

    def test_citations_attached(self) -> None:
        sigs = (_signal(0.9, "s-1"), _signal(0.8, "s-2"))
        report = WeeklyReviewBuilder().build(
            WeeklyReviewInputs(period_label="p", signals=sigs)
        )
        major = next(s for s in report.sections if s.title == "Major Signals")
        assert "[sig:s-1]" in major.citations
        assert "[sig:s-2]" in major.citations


# ----------------------- Research Progress -----------------------


class TestResearchProgress:
    def test_research_listed_with_status(self) -> None:
        r1 = _research("Q1?").start()
        r2 = _research("Q2?")
        report = WeeklyReviewBuilder().build(
            WeeklyReviewInputs(period_label="p", researches=(r1, r2))
        )
        rp = next(s for s in report.sections if s.title == "Research Progress")
        assert "[ongoing]" in rp.body or "[open]" in rp.body
        assert "Q1?" in rp.body
        assert "Q2?" in rp.body

    def test_omitted_when_no_research(self) -> None:
        report = WeeklyReviewBuilder().build(WeeklyReviewInputs(period_label="p"))
        assert not any(s.title == "Research Progress" for s in report.sections)


# ----------------------- Thesis Changes -----------------------


class TestThesisChanges:
    def test_theses_listed_with_citations(self) -> None:
        theses = (_thesis("ACME growth"), _thesis("Bear case for XYZ"))
        report = WeeklyReviewBuilder().build(
            WeeklyReviewInputs(period_label="p", theses=theses)
        )
        tc = next(s for s in report.sections if s.title == "Thesis Changes")
        assert "ACME growth" in tc.body
        assert "Bear case for XYZ" in tc.body
        assert len(tc.citations) == 2
        assert all(c.startswith("[thesis:") for c in tc.citations)

    def test_omitted_when_no_theses(self) -> None:
        report = WeeklyReviewBuilder().build(WeeklyReviewInputs(period_label="p"))
        assert not any(s.title == "Thesis Changes" for s in report.sections)


# ----------------------- Calibration Summary -----------------------


class TestCalibrationSummary:
    def test_present_when_calibration_provided(self) -> None:
        from src.research.calibration import CalibrationData

        cal = CalibrationData(
            cycle_id="wk-1",
            emitted_at="2026-07-19T00:00:00Z",
            total_signals=120,
            total_overrides=8,
            total_conflicts=2,
            total_themes=10,
            score_deltas=(),
        )
        report = WeeklyReviewBuilder().build(
            WeeklyReviewInputs(period_label="p", calibration=cal)
        )
        cs = next(s for s in report.sections if s.title == "Calibration Summary")
        assert "signals=120" in cs.body
        assert "overrides=8" in cs.body

    def test_omitted_when_no_calibration(self) -> None:
        report = WeeklyReviewBuilder().build(WeeklyReviewInputs(period_label="p"))
        assert not any(s.title == "Calibration Summary" for s in report.sections)


# ----------------------- Evidence Highlights -----------------------


class TestEvidenceHighlights:
    def test_evidences_listed_with_quality(self) -> None:
        evs = (_evidence("Filing text A"), _evidence("Filing text B"))
        report = WeeklyReviewBuilder().build(
            WeeklyReviewInputs(period_label="p", evidences=evs)
        )
        eh = next(s for s in report.sections if s.title == "Evidence Highlights")
        assert "Filing text A" in eh.body
        assert "Filing text B" in eh.body
        assert "q=" in eh.body  # quality prefix

    def test_long_content_truncated(self) -> None:
        long_content = "x" * 500
        report = WeeklyReviewBuilder().build(
            WeeklyReviewInputs(period_label="p", evidences=(_evidence(long_content),))
        )
        eh = next(s for s in report.sections if s.title == "Evidence Highlights")
        assert "..." in eh.body
        assert len(eh.body) < len(long_content) + 50

    def test_omitted_when_no_evidences(self) -> None:
        report = WeeklyReviewBuilder().build(WeeklyReviewInputs(period_label="p"))
        assert not any(s.title == "Evidence Highlights" for s in report.sections)


# ----------------------- Risks -----------------------


class TestRisks:
    def test_risks_listed_when_provided(self) -> None:
        notes = ("Calibration drift in medium band", "Source latency rising")
        report = WeeklyReviewBuilder().build(
            WeeklyReviewInputs(period_label="p", risk_notes=notes)
        )
        risks = next(s for s in report.sections if s.title == "Risks")
        assert "Calibration drift" in risks.body
        assert "Source latency" in risks.body

    def test_omitted_when_no_notes(self) -> None:
        report = WeeklyReviewBuilder().build(WeeklyReviewInputs(period_label="p"))
        assert not any(s.title == "Risks" for s in report.sections)


# ----------------------- Next Week Focus -----------------------


class TestLookahead:
    def test_lookahead_listed_when_provided(self) -> None:
        notes = ("FOMC meeting Wednesday", "Earnings: ACME, XYZ")
        report = WeeklyReviewBuilder().build(
            WeeklyReviewInputs(period_label="p", lookahead_notes=notes)
        )
        lk = next(s for s in report.sections if s.title == "Next Week Focus")
        assert "FOMC" in lk.body
        assert "ACME, XYZ" in lk.body

    def test_omitted_when_no_notes(self) -> None:
        report = WeeklyReviewBuilder().build(WeeklyReviewInputs(period_label="p"))
        assert not any(s.title == "Next Week Focus" for s in report.sections)


# ----------------------- determinism -----------------------


class TestDeterminism:
    def test_two_calls_produce_identical_reports(self) -> None:
        inputs = WeeklyReviewInputs(
            period_label="p",
            signals=(_signal(0.7, "s-1"), _signal(0.9, "s-2")),
        )
        builder = WeeklyReviewBuilder()
        r1 = builder.build(inputs)
        r2 = builder.build(inputs)
        assert r1 == r2

    def test_signal_order_does_not_affect_output(self) -> None:
        sigs = (_signal(0.3, "a"), _signal(0.9, "b"), _signal(0.6, "c"))
        reverse = tuple(reversed(sigs))
        r1 = WeeklyReviewBuilder().build(WeeklyReviewInputs(period_label="p", signals=sigs))
        r2 = WeeklyReviewBuilder().build(WeeklyReviewInputs(period_label="p", signals=reverse))
        assert r1 == r2


# ----------------------- report metadata -----------------------


class TestReportMetadata:
    def test_cycle_ids_passed_through(self) -> None:
        report = WeeklyReviewBuilder().build(
            WeeklyReviewInputs(period_label="p"),
            cycle_ids=("c-1", "c-2", "c-3"),
        )
        assert report.cycle_ids == ("c-1", "c-2", "c-3")

    def test_period_label_in_metadata(self) -> None:
        report = WeeklyReviewBuilder().build(
            WeeklyReviewInputs(period_label="Week of 2026-07-13")
        )
        assert report.period_label == "Week of 2026-07-13"

    def test_degrade_mode_propagates(self) -> None:
        report = WeeklyReviewBuilder().build(
            WeeklyReviewInputs(period_label="p"),
            degrade_mode=True,
        )
        assert report.degrade_mode is True


# ----------------------- dep inversion -----------------------


class TestDepInversion:
    def test_builder_does_not_import_runtime_internals(self) -> None:
        import re

        import src.reports.builder as mod

        source = mod.__file__ or ""
        with open(source, encoding="utf-8") as f:
            contents = f.read()
        forbidden = (
            r"from\s+src\.runtime\.executor",
            r"from\s+src\.runtime\.queue",
            r"from\s+src\.runtime\.scheduler",
            r"from\s+src\.runtime\.retry",
            r"from\s+src\.runtime\.validator",
            r"from\s+src\.runtime\.audit",
            r"from\s+src\.runtime\.dead_letter",
            r"from\s+src\.persistence",
            r"from\s+src\.workflow",
        )
        for pat in forbidden:
            assert not re.search(pat, contents), f"unexpected import: {pat}"