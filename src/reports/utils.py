"""
Shared rendering utilities — Phase 6 Checkpoint 1.

Per `13_report_template.md`:
- §2.5 — Citation format: `[sig:01HXY...]` / `[thesis:01HW2...]`.
- §2.6 — Length caps per section kind.
- §2.7 — Banned-word denylist.

These utilities are pure (no IO) so they can be unit-tested in isolation.
The renderer (`render.py`) calls into them to validate the assembled
sections.

Dependency rules:
- Pure stdlib only. No imports of `core`, `persistence`, `runtime`,
  `research`, or `workflow`.
"""

from __future__ import annotations

import re

# §2.5: citation tokens look like [sig:01HXY...] or [thesis:01HW2...].
_CITATION_RE = re.compile(r"\[(sig|thesis):([A-Za-z0-9_\-]+)\]")

# §2.6: per-section length caps (chars). Headline-style sections are
# shorter; per-entity summaries longer.
LENGTH_CAPS: dict[str, int] = {
    "headline": 100,
    "summary": 280,
    "cluster_narrative": 500,
    "body": 5000,  # upper bound for free-body sections
}

# §2.7: banned phrases (case-insensitive substring match). Empty phrase
# is filtered out below.
BANNED_PHRASES: tuple[str, ...] = tuple(
    p
    for p in (
        "we recommend",
        "we suggest buying",
        "we suggest selling",
        "target price:",
        "significantly",  # banned unless paired with a number (renderer responsibility)
        "game-changer",
        "game changer",
        "moon",
        "rocket",
        "strong quarter",  # too vague per §2.7 example
        "to the moon",
        "mooning",
    )
    if p
)


def find_citations(text: str) -> tuple[str, ...]:
    """Return all citation tokens (deduplicated, preserving order)."""
    seen: set[str] = set()
    out: list[str] = []
    for match in _CITATION_RE.finditer(text):
        token = match.group(0)
        if token not in seen:
            seen.add(token)
            out.append(token)
    return tuple(out)


def check_length_cap(body: str, section_kind: str) -> bool:
    """Return True iff `body` is within the length cap for `section_kind`.

    Length is measured in characters (not words) for predictability.
    Unknown section kinds use the "body" cap.
    """
    cap = LENGTH_CAPS.get(section_kind, LENGTH_CAPS["body"])
    return len(body) <= cap


def find_banned_phrases(text: str) -> tuple[str, ...]:
    """Return all banned phrases that appear in `text` (case-insensitive)."""
    lowered = text.lower()
    return tuple(p for p in BANNED_PHRASES if p in lowered)


def format_citation(kind: str, identifier: str) -> str:
    """Format a citation token per `13 §2.5`."""
    if kind not in {"sig", "thesis"}:
        raise ValueError(f"Unknown citation kind: {kind!r}")
    return f"[{kind}:{identifier}]"


def total_word_count(*texts: str) -> int:
    """Approximate word count across the given texts."""
    return sum(len(t.split()) for t in texts)


__all__ = [
    "BANNED_PHRASES",
    "LENGTH_CAPS",
    "check_length_cap",
    "find_banned_phrases",
    "find_citations",
    "format_citation",
    "total_word_count",
]