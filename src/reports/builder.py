"""
ReportBuilder — Phase 6 Checkpoints 1 + 2.

The `ReportBuilder` family composes Reports from Runtime and Research
outputs. This module provides:
- `ReportBuilder.build_daily_brief(...)` (Checkpoint 1)
- `WeeklyReviewBuilder.build(...)` (Checkpoint 2)

Dependency rules:
- Depends on Runtime OUTPUTS (`CycleReport`) and Research outputs
  (`CalibrationData`).
- Does NOT import runtime.* internals.
- Does NOT import workflow gates.
- Does NOT import persistence.* or scheduler.*.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from src.core.entities import Entity
from src.core.evidence import Evidence
from src.core.research import Research
from src.core.signals import Signal
from src.core.theses import Thesis
from src.reports.models import Report, ReportKind, ReportSection
from src.reports.utils import format_citation

if TYPE_CHECKING:
    from src.research.calibration import CalibrationData
    from src.runtime.cycle import CycleReport


@dataclass(frozen=True, slots=True)
class DailyBriefInputs:
    """Inputs for Daily Brief construction."""

    cycle_reports: tuple["CycleReport", ...] = ()
    signals: tuple[Signal, ...] = ()
    researches: tuple[Research, ...] = ()
    theses: tuple[Thesis, ...] = ()
    calibration: "CalibrationData | None" = None
    coverage_gaps: tuple[str, ...] = ()


class ReportBuilder:
    """Composes Daily Brief reports from Runtime + Research outputs.

    The builder is stateless; call `build_daily_brief(inputs)` per window.
    """

    def build_daily_brief(
        self,
        inputs: DailyBriefInputs,
        *,
        cycle_ids: tuple[str, ...] = (),
        agent_versions: tuple[str, ...] = (),
        prompt_versions: tuple[str, ...] = (),
        degrade_mode: bool = False,
    ) -> Report:
        """Build a Daily Brief report.

        Returns a `Report(kind=DAILY_BRIEF)` with the standard sections.
        Rendering (Markdown) is the renderer's job; this method produces
        the structured data only.
        """
        sections: list[ReportSection] = []

        # 1. Headline — neutral, factual summary.
        headline = self._compose_headline(inputs)
        sections.append(
            ReportSection(
                title="Headline",
                body=headline,
                section_kind="headline",
            )
        )

        # 2. Cycle summary — totals across cycle_reports.
        cycle_summary = self._compose_cycle_summary(inputs)
        sections.append(
            ReportSection(
                title="Cycle Summary",
                body=cycle_summary,
                section_kind="summary",
            )
        )

        # 3. Top signals — bounded excerpt with citations.
        top_signals_section = self._compose_top_signals(inputs)
        if top_signals_section is not None:
            sections.append(top_signals_section)

        # 4. Theme updates — list of Thesis interpretations.
        themes_section = self._compose_themes(inputs)
        if themes_section is not None:
            sections.append(themes_section)

        # 5. Calibration snapshot.
        if inputs.calibration is not None:
            sections.append(self._compose_calibration(inputs.calibration))

        return Report(
            kind=ReportKind.DAILY_BRIEF,
            title=self._compose_title(inputs),
            sections=tuple(sections),
            cycle_ids=cycle_ids
            or tuple(str(c.cycle_id) for c in inputs.cycle_reports),
            agent_versions=agent_versions,
            prompt_versions=prompt_versions,
            degrade_mode=degrade_mode,
            coverage_gaps=inputs.coverage_gaps,
            word_budget=5000,
        )

    # ---- per-section composers ----

    @staticmethod
    def _compose_title(inputs: DailyBriefInputs) -> str:
        n_signals = len(inputs.signals)
        n_research = len(inputs.researches)
        return f"Daily Brief — {n_signals} signals, {n_research} research items"

    @staticmethod
    def _compose_headline(inputs: DailyBriefInputs) -> str:
        if not inputs.signals:
            return "No new Signals in the window."
        # Neutral headline: counts only.
        return (
            f"{len(inputs.signals)} Signals emitted across "
            f"{len(inputs.researches)} Research investigations."
        )

    @staticmethod
    def _compose_cycle_summary(inputs: DailyBriefInputs) -> str:
        if not inputs.cycle_reports:
            return "No cycles recorded for this window."
        total_signals = sum(c.signals_emitted for c in inputs.cycle_reports)
        total_research = sum(c.research_emitted for c in inputs.cycle_reports)
        total_theses = sum(c.theses_updated for c in inputs.cycle_reports)
        return (
            f"{len(inputs.cycle_reports)} cycle(s); "
            f"{total_signals} signals, "
            f"{total_research} research, "
            f"{total_theses} thesis updates."
        )

    @staticmethod
    def _compose_top_signals(inputs: DailyBriefInputs) -> ReportSection | None:
        if not inputs.signals:
            return None
        # Sort by composite descending and take top 5.
        top = sorted(inputs.signals, key=lambda s: s.score.composite, reverse=True)[:5]
        lines: list[str] = []
        for sig in top:
            citation = format_citation("sig", str(sig.id))
            lines.append(
                f"- ({sig.score.composite:.2f}) {sig.claim} {citation}"
            )
        body = "\n".join(lines)
        return ReportSection(
            title="Top Signals",
            body=body,
            section_kind="body",
            citations=tuple(format_citation("sig", str(s.id)) for s in top),
        )

    @staticmethod
    def _compose_themes(inputs: DailyBriefInputs) -> ReportSection | None:
        if not inputs.theses:
            return None
        lines: list[str] = []
        for thesis in inputs.theses:
            citation = format_citation("thesis", str(thesis.id))
            lines.append(f"- {thesis.interpretation} {citation}")
        return ReportSection(
            title="Theme Updates",
            body="\n".join(lines),
            section_kind="body",
            citations=tuple(format_citation("thesis", str(t.id)) for t in inputs.theses),
        )

    @staticmethod
    def _compose_calibration(calibration: "CalibrationData") -> ReportSection:
        body = (
            f"signals={calibration.total_signals}; "
            f"overrides={calibration.total_overrides}; "
            f"conflicts={calibration.total_conflicts}; "
            f"themes={calibration.total_themes}"
        )
        return ReportSection(
            title="Calibration Snapshot",
            body=body,
            section_kind="summary",
        )


__all__ = [
    "DailyBriefInputs",
    "PerEntityBriefBuilder",
    "PerEntityBriefInputs",
    "ReportBuilder",
    "WeeklyReviewBuilder",
    "WeeklyReviewInputs",
]


# ============================================================================
# Weekly Review (Phase 6 Checkpoint 2)
# ============================================================================


# Weekly Review word budget per `13 §2.6`.
WEEKLY_REVIEW_WORD_BUDGET = 15_000


@dataclass(frozen=True, slots=True)
class WeeklyReviewInputs:
    """Inputs for Weekly Review construction.

    Fields:
        period_label: Human-readable label for the reporting period
            (e.g., "Week of 2026-07-13").
        signals: All Signals emitted during the week.
        researches: Research updates during the week.
        theses: Thesis updates during the week.
        evidences: Evidence objects grounding the Signals (used for the
            Evidence Highlights section).
        calibration: CalibrationData snapshot for the week (optional).
        coverage_gaps: Entity IDs with zero Signals in the window.
        risk_notes: Pre-curated risk items to surface verbatim (optional).
            The builder does NOT invent risk items; missing input → section
            is omitted.
        lookahead_notes: Pre-curated items for the "Next Week Focus"
            section. Same rule: omitted if absent.
    """

    period_label: str
    signals: tuple[Signal, ...] = ()
    researches: tuple[Research, ...] = ()
    theses: tuple[Thesis, ...] = ()
    evidences: tuple[Evidence, ...] = ()
    calibration: "CalibrationData | None" = None
    coverage_gaps: tuple[str, ...] = ()
    risk_notes: tuple[str, ...] = ()
    lookahead_notes: tuple[str, ...] = ()


class WeeklyReviewBuilder:
    """Builds Weekly Review reports deterministically.

    Deterministic contract:
    - Section order is fixed (defined by the template).
    - Signal ranking is by composite descending, then by id (stable).
    - No randomness; no time-dependent defaults beyond supplied inputs.
    """

    WEEKLY_TOP_SIGNAL_COUNT = 10

    def build(
        self,
        inputs: WeeklyReviewInputs,
        *,
        cycle_ids: tuple[str, ...] = (),
        agent_versions: tuple[str, ...] = (),
        prompt_versions: tuple[str, ...] = (),
        degrade_mode: bool = False,
    ) -> Report:
        """Build a Weekly Review Report.

        Returns a `Report(kind=WEEKLY_REVIEW)` with the canonical sections
        from `13 §4.3`. Rendering is the renderer's job.
        """
        sections: list[ReportSection] = []

        # 1. Executive Summary
        sections.append(
            ReportSection(
                title="Executive Summary",
                body=self._compose_executive_summary(inputs),
                section_kind="summary",
            )
        )

        # 2. Major Signals (top N by composite, stable tiebreak by id).
        major = self._top_signals(inputs.signals, self.WEEKLY_TOP_SIGNAL_COUNT)
        if major:
            sections.append(self._compose_major_signals(major))

        # 3. Research Progress
        if inputs.researches:
            sections.append(self._compose_research_progress(inputs.researches))

        # 4. Thesis Changes
        if inputs.theses:
            sections.append(self._compose_thesis_changes(inputs.theses))

        # 5. Calibration Summary
        if inputs.calibration is not None:
            sections.append(self._compose_calibration(inputs.calibration))

        # 6. Evidence Highlights
        if inputs.evidences:
            sections.append(self._compose_evidence_highlights(inputs.evidences))

        # 7. Risks (only if explicit notes were provided).
        if inputs.risk_notes:
            sections.append(self._compose_risks(inputs.risk_notes))

        # 8. Next Week Focus (only if explicit notes were provided).
        if inputs.lookahead_notes:
            sections.append(self._compose_lookahead(inputs.lookahead_notes))

        return Report(
            kind=ReportKind.WEEKLY_REVIEW,
            title=f"Weekly Review — {inputs.period_label}",
            sections=tuple(sections),
            cycle_ids=cycle_ids,
            agent_versions=agent_versions,
            prompt_versions=prompt_versions,
            degrade_mode=degrade_mode,
            coverage_gaps=inputs.coverage_gaps,
            word_budget=WEEKLY_REVIEW_WORD_BUDGET,
            period_label=inputs.period_label,
        )

    # ---- per-section composers ----

    @staticmethod
    def _compose_executive_summary(inputs: WeeklyReviewInputs) -> str:
        n_signals = len(inputs.signals)
        n_research = len(inputs.researches)
        n_theses = len(inputs.theses)
        return (
            f"Period: {inputs.period_label}. "
            f"{n_signals} Signals, {n_research} Research updates, "
            f"{n_theses} Thesis changes."
        )

    @staticmethod
    def _top_signals(
        signals: tuple[Signal, ...], limit: int
    ) -> tuple[Signal, ...]:
        """Return up to `limit` signals, ranked by composite desc, id asc."""
        return tuple(
            sorted(signals, key=lambda s: (-s.score.composite, str(s.id)))[:limit]
        )

    @staticmethod
    def _compose_major_signals(signals: tuple[Signal, ...]) -> ReportSection:
        lines: list[str] = []
        citations: list[str] = []
        for rank, sig in enumerate(signals, start=1):
            citation = format_citation("sig", str(sig.id))
            citations.append(citation)
            lines.append(
                f"{rank}. ({sig.score.composite:.2f}) {sig.claim} {citation}"
            )
        return ReportSection(
            title="Major Signals",
            body="\n".join(lines),
            section_kind="body",
            citations=tuple(citations),
        )

    @staticmethod
    def _compose_research_progress(researches: tuple[Research, ...]) -> ReportSection:
        lines: list[str] = []
        for r in researches:
            status = r.status.value
            lines.append(f"- [{status}] {r.question}")
        return ReportSection(
            title="Research Progress",
            body="\n".join(lines),
            section_kind="body",
        )

    @staticmethod
    def _compose_thesis_changes(theses: tuple[Thesis, ...]) -> ReportSection:
        lines: list[str] = []
        citations: list[str] = []
        for thesis in theses:
            citation = format_citation("thesis", str(thesis.id))
            citations.append(citation)
            lines.append(f"- {thesis.interpretation} {citation}")
        return ReportSection(
            title="Thesis Changes",
            body="\n".join(lines),
            section_kind="body",
            citations=tuple(citations),
        )

    @staticmethod
    def _compose_calibration(calibration: "CalibrationData") -> ReportSection:
        body = (
            f"signals={calibration.total_signals}; "
            f"overrides={calibration.total_overrides}; "
            f"conflicts={calibration.total_conflicts}; "
            f"themes={calibration.total_themes}"
        )
        return ReportSection(
            title="Calibration Summary",
            body=body,
            section_kind="summary",
        )

    @staticmethod
    def _compose_evidence_highlights(evidences: tuple[Evidence, ...]) -> ReportSection:
        lines: list[str] = []
        for ev in evidences:
            preview = ev.content if len(ev.content) <= 200 else ev.content[:197] + "..."
            lines.append(f"- (q={ev.quality.source_reliability:.2f}) {preview}")
        return ReportSection(
            title="Evidence Highlights",
            body="\n".join(lines),
            section_kind="body",
        )

    @staticmethod
    def _compose_risks(risk_notes: tuple[str, ...]) -> ReportSection:
        return ReportSection(
            title="Risks",
            body="\n".join(f"- {n}" for n in risk_notes),
            section_kind="body",
        )

    @staticmethod
    def _compose_lookahead(notes: tuple[str, ...]) -> ReportSection:
        return ReportSection(
            title="Next Week Focus",
            body="\n".join(f"- {n}" for n in notes),
            section_kind="body",
        )


# ============================================================================
# Per-Entity Brief (Phase 6 Checkpoint 3)
# ============================================================================
#
# Per the frozen Report Specification (`docs/REPORT_SPECIFICATION.md`):
#
# - The Per-Entity Brief is an Entity Snapshot, NOT a Knowledge Summary.
# - It does NOT include Knowledge, KnowledgeAccumulator, or aggregate
#   statistics beyond what is directly traceable to the anchor Entity.
# - The Thesis (if any) is the organizing principle. Signals, Evidence, and
#   Research are presented as support for the Thesis, not as independent
#   dumps.
#
# Section order (per spec §3.1):
#   Entity Overview → Current Thesis → Supporting Signals →
#   Supporting Evidence → Research Progress → Open Questions →
#   Upcoming Catalysts → Provenance


@dataclass(frozen=True, slots=True)
class PerEntityBriefInputs:
    """Inputs for Per-Entity Brief construction.

    Fields:
        anchor_entity: The Entity the report is anchored to. Required.
        signals: Candidate Signals. The builder filters to those supporting
            the current Thesis (or all signals for the entity if no
            Thesis exists).
        researches: Candidate Research items. Filtered to those whose
            `entity_ref` matches the anchor.
        theses: Candidate Theses. The builder selects the most recent
            non-terminal Thesis for the anchor.
        evidences: Candidate Evidence. The builder filters to those grounding
            the Supporting Signals.
        catalyst_notes: Caller-supplied upcoming catalysts (optional).
            Section omitted if empty.
    """

    anchor_entity: Entity
    signals: tuple[Signal, ...] = ()
    researches: tuple[Research, ...] = ()
    theses: tuple[Thesis, ...] = ()
    evidences: tuple[Evidence, ...] = ()
    catalyst_notes: tuple[str, ...] = ()


# Per-Entity Brief word budget (mirrors Weekly Review; the spec leaves
# the exact budget for Per-Entity Brief as a per-checkpoint decision).
PER_ENTITY_BRIEF_WORD_BUDGET = 5_000


class PerEntityBriefBuilder:
    """Builds Per-Entity Brief reports deterministically.

    The builder:
    - Identifies the current Thesis (latest non-terminal Thesis for the
      anchor entity).
    - Derives Supporting Signals: signals that contributed to the Thesis
      via the Thesis's evolution history's `contributing_research_ids`
      chain. If no Thesis exists, falls back to all signals referencing
      the anchor entity.
    - Derives Supporting Evidence: evidence grounding the Supporting
      Signals.
    - Includes Research Progress: research items for the anchor entity.
    - Includes Open Questions from the Thesis.
    - Includes Upcoming Catalysts (if notes supplied).

    Per the spec (§1, §2.11), the report tells ONE coherent research
    story centered on the anchor Entity. Sections are not independent
    dumps.
    """

    def build(
        self,
        inputs: PerEntityBriefInputs,
        *,
        cycle_ids: tuple[str, ...] = (),
        agent_versions: tuple[str, ...] = (),
        prompt_versions: tuple[str, ...] = (),
        degrade_mode: bool = False,
    ) -> Report:
        """Build a Per-Entity Brief Report.

        Returns a `Report(kind=PER_ENTITY_BRIEF)` with the canonical
        sections per spec §2.
        """
        entity = inputs.anchor_entity
        anchor_id = str(entity.id)

        # 1. Identify the current Thesis for this entity.
        current_thesis = self._select_current_thesis(inputs.theses, anchor_id)

        # 2. Derive Supporting Signals (filtered to those supporting the
        # Thesis, or all signals for the entity if no Thesis exists).
        supporting_signals = self._select_supporting_signals(
            current_thesis, inputs.signals, inputs.researches, anchor_id
        )

        # 3. Derive Supporting Evidence (evidence grounding the supporting
        # signals).
        supporting_evidence = self._select_supporting_evidence(
            supporting_signals, inputs.evidences
        )

        # 4. Research Progress (research for the anchor entity).
        research_items = tuple(
            r for r in inputs.researches
            if str(r.entity_ref.id) == anchor_id
        )

        # Build sections in canonical order.
        sections: list[ReportSection] = []

        # §2.1 Entity Overview
        sections.append(self._compose_entity_overview(entity, current_thesis))

        # §2.2 Current Thesis
        if current_thesis is not None:
            sections.append(self._compose_current_thesis(current_thesis))

        # §2.3 Supporting Signals
        if supporting_signals:
            sections.append(
                self._compose_supporting_signals(supporting_signals)
            )

        # §2.4 Supporting Evidence
        if supporting_evidence:
            sections.append(
                self._compose_supporting_evidence(supporting_evidence)
            )

        # §2.5 Research Progress
        if research_items:
            sections.append(self._compose_research_progress(research_items))

        # §2.6 Open Questions (from Thesis.open_questions)
        if current_thesis is not None and current_thesis.open_questions:
            sections.append(
                self._compose_open_questions(current_thesis.open_questions)
            )

        # §2.7 Upcoming Catalysts (caller-supplied)
        if inputs.catalyst_notes:
            sections.append(
                self._compose_upcoming_catalysts(inputs.catalyst_notes)
            )

        return Report(
            kind=ReportKind.PER_ENTITY_BRIEF,
            title=f"Entity Brief — {entity.name}",
            sections=tuple(sections),
            cycle_ids=cycle_ids,
            agent_versions=agent_versions,
            prompt_versions=prompt_versions,
            degrade_mode=degrade_mode,
            coverage_gaps=(),
            word_budget=PER_ENTITY_BRIEF_WORD_BUDGET,
            anchor_entity_id=anchor_id,
        )

    # ---- thesis-centric selectors ----

    @staticmethod
    def _select_current_thesis(
        theses: tuple[Thesis, ...], anchor_id: str
    ) -> Thesis | None:
        """Pick the latest non-terminal Thesis for the anchor entity.

        Sort key: (last_evolution_at, history_length, id). A Thesis with
        more evolution history ranks higher than one with the same
        timestamp but fewer entries (handles same-second timestamps).
        """
        candidates = [
            t for t in theses
            if str(t.entity_ref.id) == anchor_id
            and t.status.value not in {"superseded", "retired"}
        ]
        if not candidates:
            return None

        def sort_key(t: Thesis) -> tuple[str, int, str]:
            last_at = (
                t.evolution_history[-1].at
                if t.evolution_history
                else t.created_at
            )
            return (last_at, len(t.evolution_history), str(t.id))

        return max(candidates, key=sort_key)

    @staticmethod
    def _select_supporting_signals(
        thesis: Thesis | None,
        signals: tuple[Signal, ...],
        researches: tuple[Research, ...],
        anchor_id: str,
    ) -> tuple[Signal, ...]:
        """Select Signals that support the current Thesis.

        Algorithm:
        1. If a Thesis exists, collect `contributing_research_ids` from its
           evolution history. Resolve each contributing Research ID to the
           Research's `signal_ids`. The union of those Signal IDs is the
           "supporting" set.
        2. Filter `signals` to those whose IDs are in the supporting set
           AND whose entity matches the anchor.

        Per spec §2.3, a Signal that does not support any Thesis MUST NOT
        appear in Supporting Signals. If no Thesis exists, no signals are
        selected — the Supporting Signals section is omitted.
        """
        if thesis is None:
            return ()

        supporting_ids: set[str] = set()
        research_by_id = {str(r.id): r for r in researches}
        for evo in thesis.evolution_history:
            for rid in evo.contributing_research_ids:
                r = research_by_id.get(str(rid))
                if r is None:
                    continue
                for sid in r.signal_ids:
                    supporting_ids.add(str(sid))

        if not supporting_ids:
            return ()

        return tuple(
            s for s in signals
            if str(s.id) in supporting_ids
            and str(s.entity_ref.id) == anchor_id
        )

    @staticmethod
    def _select_supporting_evidence(
        signals: tuple[Signal, ...],
        evidences: tuple[Evidence, ...],
    ) -> tuple[Evidence, ...]:
        """Select Evidence objects grounding the given Signals.

        Iterates each Signal's `evidence_ids` and matches against the
        supplied evidence pool. Returns the matched Evidence objects in
        a deterministic order (by Evidence id).
        """
        needed: set[str] = set()
        for sig in signals:
            for eid in sig.evidence_ids:
                needed.add(str(eid))
        matched = [e for e in evidences if str(e.id) in needed]
        return tuple(sorted(matched, key=lambda e: str(e.id)))

    # ---- per-section composers ----

    @staticmethod
    def _compose_entity_overview(
        entity: Entity, thesis: Thesis | None
    ) -> ReportSection:
        lines: list[str] = []
        lines.append(f"Entity: {entity.name} (kind={entity.kind.value})")
        if entity.aliases:
            lines.append(f"Aliases: {', '.join(entity.aliases)}")
        if thesis is not None:
            lines.append(
                f"Current Thesis status: {thesis.status.value}."
            )
        else:
            lines.append(
                "Current Thesis status: none — the system has not yet formed "
                "a Thesis for this entity."
            )
        return ReportSection(
            title="Entity Overview",
            body="\n".join(lines),
            section_kind="summary",
        )

    @staticmethod
    def _compose_current_thesis(thesis: Thesis) -> ReportSection:
        citation = format_citation("thesis", str(thesis.id))
        lines = [
            f"Status: {thesis.status.value}",
            f"Interpretation: {thesis.interpretation} {citation}",
        ]
        return ReportSection(
            title="Current Thesis",
            body="\n".join(lines),
            section_kind="body",
            citations=(citation,),
        )

    @staticmethod
    def _compose_supporting_signals(signals: tuple[Signal, ...]) -> ReportSection:
        sorted_signals = sorted(
            signals, key=lambda s: (-s.score.composite, str(s.id))
        )
        lines: list[str] = []
        citations: list[str] = []
        for sig in sorted_signals:
            citation = format_citation("sig", str(sig.id))
            citations.append(citation)
            lines.append(
                f"- ({sig.score.composite:.2f}) {sig.claim} {citation}"
            )
        return ReportSection(
            title="Supporting Signals",
            body="\n".join(lines),
            section_kind="body",
            citations=tuple(citations),
        )

    @staticmethod
    def _compose_supporting_evidence(
        evidences: tuple[Evidence, ...],
    ) -> ReportSection:
        lines: list[str] = []
        for ev in evidences:
            preview = ev.content if len(ev.content) <= 200 else ev.content[:197] + "..."
            lines.append(f"- (q={ev.quality.source_reliability:.2f}) {preview}")
        return ReportSection(
            title="Supporting Evidence",
            body="\n".join(lines),
            section_kind="body",
        )

    @staticmethod
    def _compose_research_progress(researches: tuple[Research, ...]) -> ReportSection:
        lines: list[str] = []
        for r in researches:
            status = r.status.value
            lines.append(f"- [{status}] {r.question}")
        return ReportSection(
            title="Research Progress",
            body="\n".join(lines),
            section_kind="body",
        )

    @staticmethod
    def _compose_open_questions(questions: tuple[str, ...]) -> ReportSection:
        return ReportSection(
            title="Open Questions",
            body="\n".join(f"- {q}" for q in questions),
            section_kind="body",
        )

    @staticmethod
    def _compose_upcoming_catalysts(notes: tuple[str, ...]) -> ReportSection:
        return ReportSection(
            title="Upcoming Catalysts",
            body="\n".join(f"- {n}" for n in notes),
            section_kind="body",
        )