"""Tests for Report data model (Phase 6 Checkpoint 1)."""

import pytest

from src.reports.models import Report, ReportKind, ReportSection


class TestReportKind:
    def test_daily_brief_value(self) -> None:
        assert ReportKind.DAILY_BRIEF.value == "daily_brief"


class TestReportSection:
    def test_minimal_construction(self) -> None:
        s = ReportSection(title="Headline", body="text")
        assert s.title == "Headline"
        assert s.section_kind == "body"
        assert s.citations == ()

    def test_frozen(self) -> None:
        s = ReportSection(title="t", body="b")
        with pytest.raises(Exception):
            s.title = "new"  # type: ignore[misc]


class TestReport:
    def test_minimal_construction(self) -> None:
        r = Report(kind=ReportKind.DAILY_BRIEF, title="t", sections=())
        assert r.word_count == 0
        assert r.word_budget == 5000
        assert r.degrade_mode is False

    def test_word_count_sums_section_bodies(self) -> None:
        s1 = ReportSection(title="a", body="one two three")
        s2 = ReportSection(title="b", body="four five")
        r = Report(
            kind=ReportKind.DAILY_BRIEF,
            title="t",
            sections=(s1, s2),
        )
        assert r.word_count == 5

    def test_frozen(self) -> None:
        r = Report(kind=ReportKind.DAILY_BRIEF, title="t", sections=())
        with pytest.raises(Exception):
            r.title = "new"  # type: ignore[misc]


class TestDefaults:
    def test_default_word_budget(self) -> None:
        assert Report(kind=ReportKind.DAILY_BRIEF, title="t", sections=()).word_budget == 5000

    def test_default_coverage_gaps_empty(self) -> None:
        assert Report(kind=ReportKind.DAILY_BRIEF, title="t", sections=()).coverage_gaps == ()