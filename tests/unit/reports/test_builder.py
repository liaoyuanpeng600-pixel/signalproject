"""Tests for ReportBuilder (Phase 6 Checkpoint 1)."""

import pytest

from src.core.entities import Entity, EntityKind
from src.core.ids import ID
from src.core.invariants import Score
from src.core.research import Research
from src.core.signals import EntityRef, Signal, SignalDirection, SignalHorizon, SignalStatus
from src.core.theses import Thesis
from src.reports.builder import DailyBriefInputs, ReportBuilder
from src.reports.models import ReportKind, ReportSection


# ----------------------- helpers -----------------------


def _entity() -> Entity:
    return Entity.create(kind=EntityKind.COMPANY, name="ACME")


def _score(value: float) -> Score:
    return Score(value, value, value, value, value)


def _signal(composite: float = 0.7, signal_id: str = "s-1") -> Signal:
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


def _research() -> Research:
    return Research.create(
        entity_ref=EntityRef(id="e-1", kind="company"),
        question="Q?",
        signal_ids=(ID("s-1"),),
    )


def _thesis() -> Thesis:
    return Thesis.create(
        entity_ref=EntityRef(id="e-1", kind="company"),
        interpretation="ACME is a growth story.",
    )


# ----------------------- empty inputs -----------------------


class TestEmptyInputs:
    def test_builds_with_no_data(self) -> None:
        builder = ReportBuilder()
        report = builder.build_daily_brief(DailyBriefInputs())
        assert report.kind == ReportKind.DAILY_BRIEF
        assert report.sections  # at least headline + cycle summary
        assert report.word_count > 0


# ----------------------- headline -----------------------


class TestHeadline:
    def test_headline_with_no_signals(self) -> None:
        builder = ReportBuilder()
        report = builder.build_daily_brief(DailyBriefInputs())
        headline = report.sections[0]
        assert headline.title == "Headline"
        assert "No new Signals" in headline.body

    def test_headline_with_signals(self) -> None:
        builder = ReportBuilder()
        report = builder.build_daily_brief(
            DailyBriefInputs(signals=(_signal(), _signal(signal_id="s-2")))
        )
        headline = report.sections[0]
        assert "2 Signals" in headline.body


# ----------------------- cycle summary -----------------------


class TestCycleSummary:
    def test_no_cycles(self) -> None:
        builder = ReportBuilder()
        report = builder.build_daily_brief(DailyBriefInputs())
        summary = report.sections[1]
        assert summary.title == "Cycle Summary"
        assert "No cycles" in summary.body

    def test_cycles_counted(self) -> None:
        from src.core.ids import new_id
        from src.research.calibration import CalibrationData  # not used directly
        from src.runtime.cycle import CycleReport

        cycles = (
            CycleReport(
                cycle_id=new_id(),
                started_at="2026-07-19T00:00:00Z",
                completed_at="2026-07-19T00:01:00Z",
                signals_emitted=3,
                research_emitted=1,
                theses_updated=1,
                sources_loaded=0,
                entities_loaded=0,
                validation_passed=True,
                gates_total=10,
                gates_passed=10,
                gates_failed=0,
                signals_persisted=3,
                research_persisted=1,
                theses_persisted=1,
            ),
        )
        builder = ReportBuilder()
        report = builder.build_daily_brief(DailyBriefInputs(cycle_reports=cycles))
        summary = report.sections[1]
        assert "3 signals" in summary.body
        assert "1 research" in summary.body
        assert "1 thesis" in summary.body


# ----------------------- top signals -----------------------


class TestTopSignals:
    def test_no_signals_section_omitted(self) -> None:
        builder = ReportBuilder()
        report = builder.build_daily_brief(DailyBriefInputs())
        titles = [s.title for s in report.sections]
        assert "Top Signals" not in titles

    def test_top_signals_sorted_by_composite(self) -> None:
        builder = ReportBuilder()
        sigs = (
            _signal(composite=0.3, signal_id="s-low"),
            _signal(composite=0.9, signal_id="s-high"),
            _signal(composite=0.6, signal_id="s-mid"),
        )
        report = builder.build_daily_brief(DailyBriefInputs(signals=sigs))
        top = next(s for s in report.sections if s.title == "Top Signals")
        # First line should be the highest-composite signal.
        assert "s-high" in top.body.split("\n")[0]
        assert "s-low" in top.body.split("\n")[-1]

    def test_top_signals_capped_at_5(self) -> None:
        builder = ReportBuilder()
        sigs = tuple(_signal(composite=0.5, signal_id=f"s-{i}") for i in range(10))
        report = builder.build_daily_brief(DailyBriefInputs(signals=sigs))
        top = next(s for s in report.sections if s.title == "Top Signals")
        assert len([l for l in top.body.split("\n") if l.startswith("-")]) == 5

    def test_top_signals_citations_attached(self) -> None:
        builder = ReportBuilder()
        sigs = (_signal(signal_id="s-1"),)
        report = builder.build_daily_brief(DailyBriefInputs(signals=sigs))
        top = next(s for s in report.sections if s.title == "Top Signals")
        assert "[sig:s-1]" in top.citations


# ----------------------- theme updates -----------------------


class TestThemes:
    def test_no_themes_section_omitted(self) -> None:
        builder = ReportBuilder()
        report = builder.build_daily_brief(DailyBriefInputs())
        titles = [s.title for s in report.sections]
        assert "Theme Updates" not in titles

    def test_themes_listed_with_citations(self) -> None:
        builder = ReportBuilder()
        report = builder.build_daily_brief(DailyBriefInputs(theses=(_thesis(),)))
        themes = next(s for s in report.sections if s.title == "Theme Updates")
        assert "growth story" in themes.body
        assert len(themes.citations) == 1


# ----------------------- calibration snapshot -----------------------


class TestCalibrationSnapshot:
    def test_calibration_section_present_when_provided(self) -> None:
        from src.research.calibration import CalibrationData

        cal = CalibrationData(
            cycle_id="c-1",
            emitted_at="2026-07-19T00:00:00Z",
            total_signals=5,
            total_overrides=2,
            total_conflicts=1,
            total_themes=3,
            score_deltas=(),
        )
        builder = ReportBuilder()
        report = builder.build_daily_brief(DailyBriefInputs(calibration=cal))
        snap = next(s for s in report.sections if s.title == "Calibration Snapshot")
        assert "signals=5" in snap.body
        assert "overrides=2" in snap.body
        assert "conflicts=1" in snap.body

    def test_calibration_section_absent_when_not_provided(self) -> None:
        builder = ReportBuilder()
        report = builder.build_daily_brief(DailyBriefInputs())
        titles = [s.title for s in report.sections]
        assert "Calibration Snapshot" not in titles


# ----------------------- report metadata -----------------------


class TestReportMetadata:
    def test_cycle_ids_from_cycle_reports(self) -> None:
        from src.core.ids import new_id
        from src.runtime.cycle import CycleReport

        cid = new_id()
        cycles = (
            CycleReport(
                cycle_id=cid,
                started_at="2026-07-19T00:00:00Z",
                completed_at="2026-07-19T00:01:00Z",
                signals_emitted=0,
                research_emitted=0,
                theses_updated=0,
                sources_loaded=0,
                entities_loaded=0,
                validation_passed=True,
                gates_total=0,
                gates_passed=0,
                gates_failed=0,
                signals_persisted=0,
                research_persisted=0,
                theses_persisted=0,
            ),
        )
        builder = ReportBuilder()
        report = builder.build_daily_brief(DailyBriefInputs(cycle_reports=cycles))
        assert str(cid) in report.cycle_ids

    def test_coverage_gaps_propagated(self) -> None:
        builder = ReportBuilder()
        report = builder.build_daily_brief(
            DailyBriefInputs(coverage_gaps=("ent-1", "ent-2"))
        )
        assert report.coverage_gaps == ("ent-1", "ent-2")