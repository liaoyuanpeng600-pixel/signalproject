"""
Report rendering — Phase 6 Checkpoint 1.

`DailyBriefRenderer` renders a `Report(kind=DAILY_BRIEF)` to Markdown.

Rendering rules (from `13_report_template.md`):
- §2.5 — citations rendered as `[sig:...]` / `[thesis:...]` inline.
- §2.6 — section length caps enforced; section exceeding cap → render
  raises `LengthCapExceeded`.
- §2.7 — banned phrases → render raises `BannedPhraseFound`.
- §2.4 — provenance footer appended at end (cycle IDs, agent/prompt
  versions, degrade mode, coverage gaps).

The renderer is a pure function: input Report → output Markdown string.
No IO, no Store mutation.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.reports.models import Report, ReportKind, ReportSection
from src.reports.utils import (
    check_length_cap,
    find_banned_phrases,
)


class RenderError(Exception):
    """Base class for render-time errors."""


class LengthCapExceeded(RenderError):
    """A section exceeded its length cap per `13 §2.6`."""

    def __init__(self, section_title: str, section_kind: str, length: int, cap: int) -> None:
        self.section_title = section_title
        self.section_kind = section_kind
        self.length = length
        self.cap = cap
        super().__init__(
            f"Section {section_title!r} ({section_kind}) length={length} exceeds cap={cap}"
        )


class BannedPhraseFound(RenderError):
    """A banned phrase was found in the report content per `13 §2.7`."""

    def __init__(self, where: str, phrase: str) -> None:
        self.where = where
        self.phrase = phrase
        super().__init__(f"Banned phrase {phrase!r} found in {where}")


class WordBudgetExceeded(RenderError):
    """The total report word count exceeded the word budget."""

    def __init__(self, actual: int, budget: int) -> None:
        self.actual = actual
        self.budget = budget
        super().__init__(
            f"Report word count {actual} exceeds budget {budget}"
        )


@dataclass(frozen=True, slots=True)
class DailyBriefRenderer:
    """Renders Daily Brief reports to Markdown."""

    def render(self, report: Report) -> str:
        """Render a Daily Brief Report to Markdown.

        Raises:
            ValueError: If `report.kind` is not DAILY_BRIEF.
            LengthCapExceeded: If any section exceeds its length cap.
            BannedPhraseFound: If any banned phrase appears.
            WordBudgetExceeded: If the total word count exceeds budget.
        """
        if report.kind != ReportKind.DAILY_BRIEF:
            raise ValueError(
                f"DailyBriefRenderer only supports DAILY_BRIEF; got {report.kind!r}"
            )

        # Pre-flight checks: length caps and banned phrases.
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
                raise BannedPhraseFound(
                    f"section {section.title!r}", banned[0]
                )

        # Whole-report checks.
        banned = find_banned_phrases(report.title)
        if banned:
            raise BannedPhraseFound("title", banned[0])
        if report.word_count > report.word_budget:
            raise WordBudgetExceeded(report.word_count, report.word_budget)

        # Assemble Markdown.
        parts: list[str] = []
        parts.append(f"# {report.title}")
        parts.append("")

        for section in report.sections:
            parts.append(f"## {section.title}")
            parts.append("")
            parts.append(section.body)
            parts.append("")

        # Provenance footer (per §2.4).
        parts.append("## Provenance")
        parts.append("")
        parts.append(f"- Cycle IDs: {', '.join(report.cycle_ids) if report.cycle_ids else 'none'}")
        parts.append(
            f"- Agent versions: {', '.join(report.agent_versions) if report.agent_versions else 'unspecified'}"
        )
        parts.append(
            f"- Prompt versions: {', '.join(report.prompt_versions) if report.prompt_versions else 'unspecified'}"
        )
        parts.append(f"- Degrade mode: {'yes' if report.degrade_mode else 'no'}")
        parts.append(
            f"- Coverage gaps: {', '.join(report.coverage_gaps) if report.coverage_gaps else 'none'}"
        )
        parts.append("")

        return "\n".join(parts).rstrip() + "\n"


def _cap_for(section_kind: str) -> int:
    """Return the length cap for a section kind."""
    from src.reports.utils import LENGTH_CAPS

    return LENGTH_CAPS.get(section_kind, LENGTH_CAPS["body"])


__all__ = [
    "BannedPhraseFound",
    "DailyBriefRenderer",
    "LengthCapExceeded",
    "RenderError",
    "WordBudgetExceeded",
]