"""
Per-Entity Brief Renderer — Phase 6 Checkpoint 3.

`PerEntityBriefRenderer` renders a `Report(kind=PER_ENTITY_BRIEF)` to
Markdown.

Reuses every shared rendering utility introduced in Checkpoint 1
(`check_length_cap`, `find_banned_phrases`, `find_citations`,
`format_citation`) and the render errors from Checkpoint 1
(`LengthCapExceeded`, `BannedPhraseFound`, `WordBudgetExceeded`).

Validation rules (per `docs/REPORT_SPECIFICATION.md`):
- Per-section length caps enforced.
- Banned-phrase denylist enforced.
- Word-budget enforced.
- Provenance footer appended (always last).
- Anchor Entity ID surfaced in provenance.

Dependency rules:
- Depends only on `reports.models`, `reports.render`, `reports.utils`.
- Does NOT import runtime, workflow, persistence, scheduler, CLI,
  network, or LLMs.
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
class PerEntityBriefRenderer:
    """Renders Per-Entity Brief reports to Markdown."""

    def render(self, report: Report) -> str:
        """Render a Per-Entity Brief Report to Markdown.

        Raises:
            ValueError: If `report.kind` is not PER_ENTITY_BRIEF.
            ValueError: If `report.anchor_entity_id` is missing.
            LengthCapExceeded: If any section exceeds its length cap.
            BannedPhraseFound: If any banned phrase appears.
            WordBudgetExceeded: If total word count exceeds budget.
        """
        if report.kind != ReportKind.PER_ENTITY_BRIEF:
            raise ValueError(
                f"PerEntityBriefRenderer only supports PER_ENTITY_BRIEF; got {report.kind!r}"
            )
        if report.anchor_entity_id is None:
            raise ValueError(
                "Per-Entity Brief requires report.anchor_entity_id"
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
        parts.append(f"_Anchor Entity: {report.anchor_entity_id}_")
        parts.append("")

        for section in report.sections:
            parts.append(f"## {section.title}")
            parts.append("")
            parts.append(section.body)
            parts.append("")

        # Provenance footer (per Report Specification §6).
        parts.append("## Provenance")
        parts.append("")
        parts.append(
            f"- Anchor Entity ID: {report.anchor_entity_id}"
        )
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
        parts.append("")

        return "\n".join(parts).rstrip() + "\n"


__all__ = ["PerEntityBriefRenderer"]