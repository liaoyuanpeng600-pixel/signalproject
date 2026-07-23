"""Tests for WeeklyReviewRenderer (Phase 6 Checkpoint 2)."""

import pytest

from src.core.ids import new_id
from src.core.invariants import Score
from src.core.signals import EntityRef, Signal, SignalDirection, SignalHorizon, SignalStatus
from src.reports.builder import WeeklyReviewBuilder, WeeklyReviewInputs
from src.reports.models import Report, ReportKind, ReportSection
from src.reports.render import BannedPhraseFound, LengthCapExceeded, WordBudgetExceeded
from src.reports.render_weekly import WeeklyReviewRenderer


def _minimal_report() -> Report:
    return WeeklyReviewBuilder().build(
        WeeklyReviewInputs(period_label="Week of 2026-07-13")
    )


# ----------------------- happy path -----------------------


class TestHappyPath:
    def test_renders_markdown(self) -> None:
        md = WeeklyReviewRenderer().render(_minimal_report())
        assert md.startswith("# Weekly Review")
        assert "Week of 2026-07-13" in md

    def test_section_order(self) -> None:
        # Order in the rendered Markdown must be:
        # Executive Summary → (other sections) → Provenance.
        report = WeeklyReviewBuilder().build(
            WeeklyReviewInputs(
                period_label="p",
                risk_notes=("r1",),
                lookahead_notes=("l1",),
            )
        )
        md = WeeklyReviewRenderer().render(report)
        es_pos = md.find("## Executive Summary")
        risks_pos = md.find("## Risks")
        lookahead_pos = md.find("## Next Week Focus")
        prov_pos = md.find("## Provenance")
        assert es_pos < risks_pos < lookahead_pos < prov_pos

    def test_renders_provenance_footer(self) -> None:
        report = Report(
            kind=ReportKind.WEEKLY_REVIEW,
            title="Weekly Review — p",
            sections=(),
            cycle_ids=("c-1", "c-2"),
            agent_versions=("v1.0",),
            prompt_versions=("p1.0",),
            degrade_mode=False,
            coverage_gaps=("ent-x",),
            period_label="p",
        )
        md = WeeklyReviewRenderer().render(report)
        assert "## Provenance" in md
        assert "c-1" in md
        assert "v1.0" in md
        assert "p1.0" in md
        assert "ent-x" in md

    def test_period_label_in_italic(self) -> None:
        md = WeeklyReviewRenderer().render(_minimal_report())
        assert "_Period:" in md

    def test_no_coverage_gaps_renders_none(self) -> None:
        md = WeeklyReviewRenderer().render(_minimal_report())
        assert "Coverage gaps: none" in md


# ----------------------- kind validation -----------------------


class TestKindValidation:
    def test_rejects_daily_brief(self) -> None:
        report = Report(kind=ReportKind.DAILY_BRIEF, title="t", sections=())
        with pytest.raises(ValueError):
            WeeklyReviewRenderer().render(report)


# ----------------------- length cap enforcement -----------------------


class TestLengthCapEnforcement:
    def test_summary_section_over_cap_raises(self) -> None:
        report = Report(
            kind=ReportKind.WEEKLY_REVIEW,
            title="t",
            sections=(ReportSection(title="s", body="x" * 281, section_kind="summary"),),
            period_label="p",
        )
        with pytest.raises(LengthCapExceeded):
            WeeklyReviewRenderer().render(report)

    def test_summary_within_cap_renders(self) -> None:
        report = Report(
            kind=ReportKind.WEEKLY_REVIEW,
            title="t",
            sections=(ReportSection(title="s", body="x" * 280, section_kind="summary"),),
            period_label="p",
        )
        md = WeeklyReviewRenderer().render(report)
        assert "x" * 280 in md


# ----------------------- banned phrase enforcement -----------------------


class TestBannedPhraseEnforcement:
    def test_section_banned_raises(self) -> None:
        report = Report(
            kind=ReportKind.WEEKLY_REVIEW,
            title="t",
            sections=(
                ReportSection(
                    title="Executive Summary",
                    body="We recommend buying more ACME.",
                    section_kind="summary",
                ),
            ),
            period_label="p",
        )
        with pytest.raises(BannedPhraseFound):
            WeeklyReviewRenderer().render(report)

    def test_title_banned_raises(self) -> None:
        report = Report(
            kind=ReportKind.WEEKLY_REVIEW,
            title="Weekly Review — to the moon",
            sections=(),
            period_label="p",
        )
        with pytest.raises(BannedPhraseFound):
            WeeklyReviewRenderer().render(report)

    def test_clean_text_renders(self) -> None:
        report = Report(
            kind=ReportKind.WEEKLY_REVIEW,
            title="Weekly Review",
            sections=(
                ReportSection(
                    title="Executive Summary",
                    body="ACME reported EPS +14% vs consensus.",
                    section_kind="summary",
                ),
            ),
            period_label="p",
        )
        md = WeeklyReviewRenderer().render(report)
        assert "EPS +14%" in md


# ----------------------- word budget enforcement -----------------------


class TestWordBudget:
    def test_word_budget_exceeded_raises(self) -> None:
        body = " ".join(["word"] * 100)
        report = Report(
            kind=ReportKind.WEEKLY_REVIEW,
            title="t",
            word_budget=10,
            sections=(
                ReportSection(title="s", body=body, section_kind="body"),
            ),
            period_label="p",
        )
        with pytest.raises(WordBudgetExceeded):
            WeeklyReviewRenderer().render(report)

    def test_word_budget_within_renders(self) -> None:
        report = Report(
            kind=ReportKind.WEEKLY_REVIEW,
            title="t",
            sections=(
                ReportSection(title="s", body="short body", section_kind="body"),
            ),
            period_label="p",
        )
        WeeklyReviewRenderer().render(report)


# ----------------------- dep inversion -----------------------


class TestDepInversion:
    def test_renderer_does_not_import_forbidden_modules(self) -> None:
        import re

        import src.reports.render_weekly as mod

        source = mod.__file__ or ""
        with open(source, encoding="utf-8") as f:
            contents = f.read()
        forbidden = (
            r"from\s+src\.runtime",
            r"from\s+src\.workflow",
            r"from\s+src\.persistence",
            r"from\s+src\.scheduler",
        )
        for pat in forbidden:
            assert not re.search(pat, contents), f"unexpected import: {pat}"

    def test_renderer_uses_shared_utils(self) -> None:
        """Reuse Checkpoint 1 utilities (per task requirements)."""
        import re

        import src.reports.render_weekly as mod

        source = mod.__file__ or ""
        with open(source, encoding="utf-8") as f:
            contents = f.read()
        # Must import the shared utilities from Checkpoint 1.
        assert re.search(
            r"from\s+src\.reports\.utils\s+import", contents
        ), "renderer must reuse Checkpoint 1 utilities"
        assert re.search(
            r"from\s+src\.reports\.render\s+import", contents
        ), "renderer must reuse Checkpoint 1 render errors"


# ----------------------- integration: builder + renderer -----------------------


class TestEndToEnd:
    def test_full_weekly_review(self) -> None:
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
        inputs = WeeklyReviewInputs(
            period_label="Week of 2026-07-13",
            signals=tuple(
                Signal.create(
                    entity_ref=EntityRef(id="e-1", kind="company"),
                    type="capital_action",
                    claim=f"claim {i}",
                    evidence_ids=(new_id(),),
                    direction=SignalDirection.BULLISH,
                    horizon=SignalHorizon.SHORT,
                    score=Score(0.5 + i * 0.05, 0.5, 0.5, 0.5, 0.5),
                    status=SignalStatus.ACTIVE,
                    id=new_id(),
                )
                for i in range(5)
            ),
            calibration=cal,
            risk_notes=("Calibration drift",),
            lookahead_notes=("FOMC meeting",),
        )
        report = WeeklyReviewBuilder().build(inputs)
        md = WeeklyReviewRenderer().render(report)
        assert md.startswith("# Weekly Review")
        assert "## Executive Summary" in md
        assert "## Major Signals" in md
        assert "## Calibration Summary" in md
        assert "## Risks" in md
        assert "## Next Week Focus" in md
        assert "## Provenance" in md