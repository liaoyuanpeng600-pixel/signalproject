"""
Report data model — Phase 6 Checkpoint 1.

`Report` is the canonical data structure for every SIGNAL report. Each
report has:
- A `kind` (currently only DAILY_BRIEF; future: WEEKLY_REVIEW,
  PER_ENTITY_BRIEF).
- A list of `ReportSection` objects in render order.
- Provenance metadata (cycle IDs, agent/prompt versions, degrade mode).
- A length budget (in words) enforced by the renderer.

This module defines the data only. Rendering is in `render.py`;
construction is in `builder.py`; rendering utilities (banned-word,
citation-format, length-cap enforcement) are in `utils.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ReportKind(str, Enum):
    """Canonical report kinds per `13_report_template.md`."""

    DAILY_BRIEF = "daily_brief"
    WEEKLY_REVIEW = "weekly_review"
    PER_ENTITY_BRIEF = "per_entity_brief"


@dataclass(frozen=True, slots=True)
class ReportSection:
    """A single section of a Report.

    Fields:
        title: Section heading (≤100 chars for headline-style sections).
        body: Section body text. May include Markdown inline citations
            (`[sig:...]`, `[thesis:...]`) per `13 §2.5`.
        section_kind: Optional tag classifying the section (e.g.,
            "headline", "summary", "calibration"). Used by the renderer
            to apply the right length cap.
        citations: Inline citation tokens referenced by this section.
            The renderer validates these against the available Signals
            and Theses (if provided).
    """

    title: str
    body: str
    section_kind: str = "body"
    citations: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Report:
    """A complete SIGNAL report (Daily Brief, Weekly Review, or Per-Entity Brief).

    Fields:
        kind: The report kind.
        title: Top-level title.
        sections: Sections in render order.
        cycle_ids: Cycle IDs covered by this report (for provenance).
        agent_versions: Agent versions used (for provenance).
        prompt_versions: Prompt versions used (for provenance).
        degrade_mode: True if any cycle ran in degrade mode.
        coverage_gaps: Entity IDs that had zero Signals in the window.
        word_budget: Maximum total word count (5,000 for Daily Brief,
            15,000 for Weekly Review per `13 §2.6`).
        period_label: Optional human-readable label for the reporting period
            (e.g., "Week of 2026-07-13"). Used by Weekly Review.
        anchor_entity_id: Optional anchor Entity ID for Per-Entity Brief.
            Required when kind == PER_ENTITY_BRIEF.
    """

    kind: ReportKind
    title: str
    sections: tuple[ReportSection, ...]
    cycle_ids: tuple[str, ...] = ()
    agent_versions: tuple[str, ...] = ()
    prompt_versions: tuple[str, ...] = ()
    degrade_mode: bool = False
    coverage_gaps: tuple[str, ...] = ()
    word_budget: int = 5000
    period_label: str | None = None
    anchor_entity_id: str | None = None

    @property
    def word_count(self) -> int:
        """Approximate word count across all section bodies."""
        return sum(len(s.body.split()) for s in self.sections)


__all__ = ["Report", "ReportKind", "ReportSection"]