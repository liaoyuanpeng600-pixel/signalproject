"""Tests for PerEntityBriefRenderer (Phase 6 Checkpoint 3)."""

import pytest

from src.core.entities import Entity, EntityKind
from src.core.ids import ID
from src.reports.builder import PerEntityBriefBuilder, PerEntityBriefInputs
from src.reports.models import Report, ReportKind, ReportSection
from src.reports.render import BannedPhraseFound, LengthCapExceeded, WordBudgetExceeded
from src.reports.render_entity import PerEntityBriefRenderer


def _entity() -> Entity:
    return Entity.create(kind=EntityKind.COMPANY, name="ACME", id=ID("e-1"))


def _minimal_report() -> Report:
    return PerEntityBriefBuilder().build(
        PerEntityBriefInputs(anchor_entity=_entity())
    )


# ----------------------- happy path -----------------------


class TestHappyPath:
    def test_renders_markdown(self) -> None:
        md = PerEntityBriefRenderer().render(_minimal_report())
        assert md.startswith("# Entity Brief")
        assert "ACME" in md

    def test_renders_anchor_in_italic(self) -> None:
        md = PerEntityBriefRenderer().render(_minimal_report())
        assert "_Anchor Entity:" in md
        assert "e-1" in md

    def test_provenance_footer_present(self) -> None:
        md = PerEntityBriefRenderer().render(_minimal_report())
        assert "## Provenance" in md
        assert "Anchor Entity ID: e-1" in md

    def test_provenance_metadata_propagated(self) -> None:
        report = PerEntityBriefBuilder().build(
            PerEntityBriefInputs(anchor_entity=_entity()),
            cycle_ids=("c-1",),
            agent_versions=("v1.0",),
            prompt_versions=("p1.0",),
            degrade_mode=False,
        )
        md = PerEntityBriefRenderer().render(report)
        assert "c-1" in md
        assert "v1.0" in md
        assert "p1.0" in md
        assert "Degrade mode: no" in md


# ----------------------- kind validation -----------------------


class TestKindValidation:
    def test_rejects_daily_brief(self) -> None:
        report = Report(kind=ReportKind.DAILY_BRIEF, title="t", sections=())
        with pytest.raises(ValueError):
            PerEntityBriefRenderer().render(report)

    def test_rejects_weekly_review(self) -> None:
        report = Report(kind=ReportKind.WEEKLY_REVIEW, title="t", sections=())
        with pytest.raises(ValueError):
            PerEntityBriefRenderer().render(report)


# ----------------------- anchor_entity_id validation -----------------------


class TestAnchorValidation:
    def test_rejects_missing_anchor_entity_id(self) -> None:
        report = Report(kind=ReportKind.PER_ENTITY_BRIEF, title="t", sections=())
        with pytest.raises(ValueError):
            PerEntityBriefRenderer().render(report)


# ----------------------- length cap enforcement -----------------------


class TestLengthCapEnforcement:
    def test_summary_section_over_cap_raises(self) -> None:
        report = Report(
            kind=ReportKind.PER_ENTITY_BRIEF,
            title="t",
            sections=(ReportSection(title="s", body="x" * 281, section_kind="summary"),),
            anchor_entity_id="e-1",
        )
        with pytest.raises(LengthCapExceeded):
            PerEntityBriefRenderer().render(report)

    def test_summary_within_cap_renders(self) -> None:
        report = Report(
            kind=ReportKind.PER_ENTITY_BRIEF,
            title="t",
            sections=(ReportSection(title="s", body="x" * 280, section_kind="summary"),),
            anchor_entity_id="e-1",
        )
        md = PerEntityBriefRenderer().render(report)
        assert "x" * 280 in md


# ----------------------- banned phrase enforcement -----------------------


class TestBannedPhraseEnforcement:
    def test_section_banned_raises(self) -> None:
        report = Report(
            kind=ReportKind.PER_ENTITY_BRIEF,
            title="t",
            sections=(
                ReportSection(
                    title="Entity Overview",
                    body="We recommend holding ACME.",
                    section_kind="summary",
                ),
            ),
            anchor_entity_id="e-1",
        )
        with pytest.raises(BannedPhraseFound):
            PerEntityBriefRenderer().render(report)

    def test_title_banned_raises(self) -> None:
        report = Report(
            kind=ReportKind.PER_ENTITY_BRIEF,
            title="Entity Brief — to the moon",
            sections=(),
            anchor_entity_id="e-1",
        )
        with pytest.raises(BannedPhraseFound):
            PerEntityBriefRenderer().render(report)

    def test_clean_text_renders(self) -> None:
        report = Report(
            kind=ReportKind.PER_ENTITY_BRIEF,
            title="Entity Brief — ACME",
            sections=(
                ReportSection(
                    title="Entity Overview",
                    body="ACME reported EPS +14% vs consensus.",
                    section_kind="summary",
                ),
            ),
            anchor_entity_id="e-1",
        )
        md = PerEntityBriefRenderer().render(report)
        assert "EPS +14%" in md


# ----------------------- word budget enforcement -----------------------


class TestWordBudget:
    def test_word_budget_exceeded_raises(self) -> None:
        body = " ".join(["word"] * 100)
        report = Report(
            kind=ReportKind.PER_ENTITY_BRIEF,
            title="t",
            word_budget=10,
            sections=(
                ReportSection(title="s", body=body, section_kind="body"),
            ),
            anchor_entity_id="e-1",
        )
        with pytest.raises(WordBudgetExceeded):
            PerEntityBriefRenderer().render(report)

    def test_word_budget_within_renders(self) -> None:
        report = Report(
            kind=ReportKind.PER_ENTITY_BRIEF,
            title="t",
            sections=(
                ReportSection(title="s", body="short", section_kind="body"),
            ),
            anchor_entity_id="e-1",
        )
        PerEntityBriefRenderer().render(report)


# ----------------------- dep inversion -----------------------


class TestDepInversion:
    def test_renderer_does_not_import_forbidden_modules(self) -> None:
        import re

        import src.reports.render_entity as mod

        source = mod.__file__ or ""
        with open(source, encoding="utf-8") as f:
            contents = f.read()
        import_re = re.compile(
            r"^\s*(?:from\s+src\.runtime|from\s+src\.workflow|from\s+src\.persistence|from\s+src\.scheduler)",
            re.MULTILINE,
        )
        matches = import_re.findall(contents)
        assert not matches, f"unexpected import: {matches}"

    def test_renderer_uses_shared_utils(self) -> None:
        import re

        import src.reports.render_entity as mod

        source = mod.__file__ or ""
        with open(source, encoding="utf-8") as f:
            contents = f.read()
        # Must import shared utilities from Checkpoint 1.
        assert re.search(
            r"^\s*from\s+src\.reports\.utils\s+import", contents, re.MULTILINE
        ), "renderer must reuse Checkpoint 1 utilities"
        assert re.search(
            r"^\s*from\s+src\.reports\.render\s+import", contents, re.MULTILINE
        ), "renderer must reuse Checkpoint 1 render errors"

    def test_renderer_does_not_import_knowledge(self) -> None:
        """Per-Entity Brief is an Entity Snapshot, not a Knowledge Summary."""
        import re

        import src.reports.render_entity as mod

        source = mod.__file__ or ""
        with open(source, encoding="utf-8") as f:
            contents = f.read()
        import_re = re.compile(
            r"^\s*(?:from\s+src\.core\.knowledge|import\s+src\.core\.knowledge)",
            re.MULTILINE,
        )
        matches = import_re.findall(contents)
        assert not matches, f"unexpected knowledge import: {matches}"


# ----------------------- integration: builder + renderer -----------------------


class TestEndToEnd:
    def test_full_entity_brief(self) -> None:
        from src.core.evidence import Evidence, Quality
        from src.core.invariants import Score
        from src.core.lifecycle import ThesisStatus
        from src.core.research import Research
        from src.core.signals import EntityRef, Signal, SignalDirection, SignalHorizon, SignalStatus
        from src.core.theses import Thesis

        sig = Signal.create(
            entity_ref=EntityRef(id="e-1", kind="company"),
            type="capital_action",
            claim="ACME dividend +10%",
            evidence_ids=(ID("ev-1"),),
            direction=SignalDirection.BULLISH,
            horizon=SignalHorizon.SHORT,
            score=Score(0.85, 0.8, 0.9, 0.7, 0.8),
            status=SignalStatus.ACTIVE,
            id=ID("s-1"),
        )
        research = Research.create(
            entity_ref=EntityRef(id="e-1", kind="company"),
            question="What is ACME's growth trajectory?",
            signal_ids=(sig.id,),
            id=ID("r-1"),
        )
        thesis = Thesis.create(
            entity_ref=EntityRef(id="e-1", kind="company"),
            interpretation="ACME is a growth story",
            id=ID("t-1"),
        )
        evolved = thesis.evolve(
            new_interpretation="ACME is a growth story (refined)",
            contributing_research_ids=(research.id,),
            by="system",
            rationale="r",
        )
        with_q = evolved.hold_with_open_question("Need Q3 data")
        ev = Evidence.create(
            source_ids=(ID("src-1"),),
            content="Filing text",
            quality=Quality(0.9, 0.9, 0.9),
            id=ID("ev-1"),
        )
        inputs = PerEntityBriefInputs(
            anchor_entity=_entity(),
            signals=(sig,),
            researches=(research,),
            theses=(with_q,),
            evidences=(ev,),
            catalyst_notes=("Earnings Aug 5",),
        )
        report = PerEntityBriefBuilder().build(inputs)
        md = PerEntityBriefRenderer().render(report)
        # Required sections all present.
        for section_title in (
            "Entity Overview",
            "Current Thesis",
            "Supporting Signals",
            "Supporting Evidence",
            "Research Progress",
            "Open Questions",
            "Upcoming Catalysts",
            "Provenance",
        ):
            assert f"## {section_title}" in md, f"missing: {section_title}"

    def test_minimal_anchor_only(self) -> None:
        """Minimal inputs → Entity Overview + Provenance only."""
        report = PerEntityBriefBuilder().build(
            PerEntityBriefInputs(anchor_entity=_entity())
        )
        md = PerEntityBriefRenderer().render(report)
        assert "## Entity Overview" in md
        assert "## Provenance" in md
        # No Thesis → these sections absent.
        assert "## Current Thesis" not in md
        assert "## Supporting Signals" not in md
        assert "## Supporting Evidence" not in md
        assert "## Open Questions" not in md
        assert "## Upcoming Catalysts" not in md