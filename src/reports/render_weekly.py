"""
Weekly Review Renderer — Phase 6 Checkpoint 2.

`WeeklyReviewRenderer` renders a `Report(kind=WEEKLY_REVIEW)` to Markdown.

Reuses every shared rendering utility introduced in Checkpoint 1
(`check_length_cap`, `find_banned_phrases`, `find_citations`,
`format_citation`). The renderer is a pure function: input Report →
output Markdown string. No IO, no Store mutation.

Validation rules (per `13 §2.4–2.7`):
- Section length caps enforced.
- Banned-phrase denylist enforced.
- Word-budget (15,000 for Weekly Review) enforced.
- Provenance footer appended (per §2.4).

Dependency rules:
- Depends only on `reports.models`, `reports.utils`.
- Does NOT import runtime, workflow, persistence, scheduler, CLI, network,
  or LLMs.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.reports.models import Report, ReportKind
from src.reports.render import (
    BannedPhraseFound,
    LengthCapExceeded,
    WordBudgetExceeded,
    _cap_for,
)
from src.reports.utils import check_length_cap, find_banned_phrases


@dataclass(frozen=True, slots=True)
class WeeklyReviewRenderer:
    """Renders Weekly Review reports to Markdown."""

    def render(self, report: Report) -> str:
        """Render a Weekly Review Report to Markdown.

        Raises:
            ValueError: If `report.kind` is not WEEKLY_REVIEW.
            LengthCapExceeded: If any section exceeds its length cap.
            BannedPhraseFound: If any banned phrase appears.
            WordBudgetExceeded: If total word count exceeds budget.
        """
        if report.kind != ReportKind.WEEKLY_REVIEW:
            raise ValueError(
                f"WeeklyReviewRenderer only supports WEEKLY_REVIEW; got {report.kind!r}"
            )

        # Pre-flight: per-section length caps and banned phrases.
        for section in report.sections:
            if not check_length_cap(section.body, section.section_kind):
                raise LengthCapExceeded(
                    section.title,
                    section.section_kind,
                    len(section.body),
                    _cap_for(section.section_kind),
                )
            banned = find_banned_phrases(section.body)
            if banned:
                raise BannedPhraseFound(f"section {section.title!r}", banned[0])

        # Whole-report: title banned-phrase and word-budget.
        banned = find_banned_phrases(report.title)
        if banned:
            raise BannedPhraseFound("title", banned[0])
        if report.word_count > report.word_budget:
            raise WordBudgetExceeded(report.word_count, report.word_budget)

        # Assemble Markdown.
        parts: list[str] = []
        parts.append(f"# {report.title}")
        parts.append("")
        if report.period_label:
            parts.append(f"_Period: {report.period_label}_")
            parts.append("")

        for section in report.sections:
            parts.append(f"## {section.title}")
            parts.append("")
            parts.append(section.body)
            parts.append("")

        # Provenance footer (per §2.4).
        parts.append("## Provenance")
        parts.append("")
        parts.append(
            f"- Cycle IDs: {', '.join(report.cycle_ids) if report.cycle_ids else 'none'}"
        )
        parts.append(
            f"- Agent versions: "
            f"{', '.join(report.agent_versions) if report.agent_versions else 'unspecified'}"
        )
        parts.append(
            f"- Prompt versions: "
            f"{', '.join(report.prompt_versions) if report.prompt_versions else 'unspecified'}"
        )
        parts.append(f"- Degrade mode: {'yes' if report.degrade_mode else 'no'}")
        parts.append(
            f"- Coverage gaps: "
            f"{', '.join(report.coverage_gaps) if report.coverage_gaps else 'none'}"
        )
        parts.append("")

        return "\n".join(parts).rstrip() + "\n"


__all__ = ["WeeklyReviewRenderer"]