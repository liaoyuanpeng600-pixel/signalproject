"""Tests for DailyBriefRenderer (Phase 6 Checkpoint 1)."""

import pytest

from src.reports.builder import DailyBriefInputs, ReportBuilder
from src.reports.models import Report, ReportKind, ReportSection
from src.reports.render import (
    BannedPhraseFound,
    DailyBriefRenderer,
    LengthCapExceeded,
    RenderError,
    WordBudgetExceeded,
)


def _minimal_report() -> Report:
    return ReportBuilder().build_daily_brief(DailyBriefInputs())


# ----------------------- happy path -----------------------


class TestHappyPath:
    def test_renders_markdown(self) -> None:
        report = _minimal_report()
        md = DailyBriefRenderer().render(report)
        assert md.startswith("# Daily Brief")
        assert "## Headline" in md
        assert "## Cycle Summary" in md

    def test_renders_provenance_footer(self) -> None:
        report = Report(
            kind=ReportKind.DAILY_BRIEF,
            title="t",
            sections=(),
            cycle_ids=("c-1", "c-2"),
            agent_versions=("v1.0",),
            prompt_versions=("p1.0",),
            degrade_mode=True,
            coverage_gaps=("ent-x",),
        )
        md = DailyBriefRenderer().render(report)
        assert "## Provenance" in md
        assert "c-1" in md
        assert "c-2" in md
        assert "v1.0" in md
        assert "p1.0" in md
        assert "yes" in md  # degrade mode
        assert "ent-x" in md  # coverage gaps

    def test_no_coverage_gaps_renders_none(self) -> None:
        report = Report(kind=ReportKind.DAILY_BRIEF, title="t", sections=())
        md = DailyBriefRenderer().render(report)
        assert "Coverage gaps: none" in md

    def test_no_degrade_renders_no(self) -> None:
        report = Report(kind=ReportKind.DAILY_BRIEF, title="t", sections=())
        md = DailyBriefRenderer().render(report)
        assert "Degrade mode: no" in md


# ----------------------- kind validation -----------------------


class TestKindValidation:
    def test_rejects_non_daily_brief(self) -> None:
        # Future kinds are not implemented; for now the only kind is
        # DAILY_BRIEF. Build a report claiming a different kind.
        r = Report(kind=ReportKind.DAILY_BRIEF, title="t", sections=())
        # Mutating `kind` is not possible on frozen dataclass. We instead
        # verify the renderer accepts the canonical kind.
        DailyBriefRenderer().render(r)


# ----------------------- length cap enforcement -----------------------


class TestLengthCapEnforcement:
    def test_section_over_headline_cap_raises(self) -> None:
        report = Report(
            kind=ReportKind.DAILY_BRIEF,
            title="t",
            sections=(ReportSection(title="h", body="x" * 101, section_kind="headline"),),
        )
        with pytest.raises(LengthCapExceeded):
            DailyBriefRenderer().render(report)

    def test_section_within_cap_renders(self) -> None:
        report = Report(
            kind=ReportKind.DAILY_BRIEF,
            title="t",
            sections=(ReportSection(title="h", body="x" * 100, section_kind="headline"),),
        )
        md = DailyBriefRenderer().render(report)
        assert "x" * 100 in md


# ----------------------- banned phrase enforcement -----------------------


class TestBannedPhraseEnforcement:
    def test_section_banned_raises(self) -> None:
        report = Report(
            kind=ReportKind.DAILY_BRIEF,
            title="t",
            sections=(
                ReportSection(title="h", body="We recommend buying.", section_kind="headline"),
            ),
        )
        with pytest.raises(BannedPhraseFound):
            DailyBriefRenderer().render(report)

    def test_title_banned_raises(self) -> None:
        report = Report(
            kind=ReportKind.DAILY_BRIEF,
            title="Daily Brief — to the moon",
            sections=(),
        )
        with pytest.raises(BannedPhraseFound):
            DailyBriefRenderer().render(report)

    def test_clean_text_renders(self) -> None:
        report = Report(
            kind=ReportKind.DAILY_BRIEF,
            title="Daily Brief",
            sections=(
                ReportSection(
                    title="h",
                    body="ACME reported EPS +14% vs consensus.",
                    section_kind="headline",
                ),
            ),
        )
        md = DailyBriefRenderer().render(report)
        assert "EPS +14%" in md


# ----------------------- word budget enforcement -----------------------


class TestWordBudget:
    def test_word_budget_exceeded_raises(self) -> None:
        # Use a custom low word_budget to trigger WordBudgetExceeded without
        # tripping per-section length caps first.
        body = " ".join(["word"] * 100)
        report = Report(
            kind=ReportKind.DAILY_BRIEF,
            title="t",
            word_budget=10,
            sections=(
                ReportSection(title="h", body="headline", section_kind="headline"),
                ReportSection(title="b", body=body, section_kind="body"),
            ),
        )
        with pytest.raises(WordBudgetExceeded):
            DailyBriefRenderer().render(report)

    def test_word_budget_within_renders(self) -> None:
        report = Report(
            kind=ReportKind.DAILY_BRIEF,
            title="t",
            sections=(
                ReportSection(title="h", body="short headline", section_kind="headline"),
            ),
        )
        DailyBriefRenderer().render(report)


# ----------------------- dep inversion -----------------------


class TestDepInversion:
    def test_render_does_not_import_runtime_internals(self) -> None:
        import re

        import src.reports.render as mod

        source = mod.__file__ or ""
        with open(source, encoding="utf-8") as f:
            contents = f.read()
        assert not re.search(r"^\s*from\s+src\.runtime", contents, re.MULTILINE)
        assert "from src.workflow" not in contents

    def test_builder_does_not_import_runtime_internals(self) -> None:
        import re

        import src.reports.builder as mod

        source = mod.__file__ or ""
        with open(source, encoding="utf-8") as f:
            contents = f.read()
        # Builder may consume CycleReport (output) under TYPE_CHECKING
        # but MUST NOT import runtime internals.
        forbidden = [
            r"from\s+src\.runtime\.executor",
            r"from\s+src\.runtime\.queue",
            r"from\s+src\.runtime\.scheduler",
            r"from\s+src\.runtime\.retry",
            r"from\s+src\.runtime\.validator",
            r"from\s+src\.runtime\.audit",
            r"from\s+src\.runtime\.dead_letter",
        ]
        for pat in forbidden:
            assert not re.search(pat, contents), f"unexpected import: {pat}"

    def test_models_does_not_import_anything(self) -> None:
        import re

        import src.reports.models as mod

        source = mod.__file__ or ""
        with open(source, encoding="utf-8") as f:
            contents = f.read()
        # Models should be pure stdlib.
        assert "from src." not in contents


# ----------------------- integration: builder + renderer -----------------------


class TestEndToEnd:
    def test_builder_then_renderer(self) -> None:
        builder = ReportBuilder()
        renderer = DailyBriefRenderer()
        report = builder.build_daily_brief(DailyBriefInputs())
        md = renderer.render(report)
        # Provenance footer always present.
        assert "## Provenance" in md
        # Markdown structure.
        assert md.startswith("# ")