"""
Evidence type per Object Model §3.

Evidence is the only currency that grounds conclusions. Evidence is IMMUTABLE:
once produced, it is never edited, rewritten, or reinterpreted. Provenance and
quality are recorded at capture and never lost.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum

from src.core.ids import ID, new_id
from src.core.timestamps import now_utc


class SourceType(str, Enum):
    """Mirrors SourceType from sources; mirrors Evidence.source_type enum."""

    REGULATORY_FILING = "regulatory_filing"
    NEWS_ARTICLE = "news_article"
    EARNINGS_CALL = "earnings_call"
    PRESS_RELEASE = "press_release"
    SOCIAL_MEDIA = "social_media"
    BLOG_POST = "blog_post"
    RESEARCH_REPORT = "research_report"
    GOVERNMENT_DATA = "government_data"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class Quality:
    """Quality metadata for Evidence.

    Captured at the time Evidence is produced; never modified thereafter.
    """

    source_reliability: float  # 0.0–1.0
    content_completeness: float  # 0.0–1.0
    retrieval_confidence: float  # 0.0–1.0

    def __post_init__(self) -> None:
        for field_name in ("source_reliability", "content_completeness", "retrieval_confidence"):
            value = getattr(self, field_name)
            if not (0.0 <= value <= 1.0):
                raise ValueError(
                    f"Quality.{field_name} must be in [0.0, 1.0], got {value}"
                )


@dataclass(frozen=True, slots=True)
class Evidence:
    """An immutable, retrievable information unit.

    Evidence is frozen: once produced, it cannot be modified. Any "change" to
    Evidence is captured as a new Evidence object (with a correction Signal
    referencing the new one).
    """

    id: ID
    source_ids: tuple[ID, ...]  # At least one Source (INV-1 implicitly)
    content: str  # Verbatim from the Source
    quality: Quality
    retrieved_at: str = field(default_factory=now_utc)
    retrievable: bool = True
    source_type: SourceType | None = None  # Optional, mirrors Evidence.source_type
    char_offset: tuple[int, int] | None = None  # [start, end] within source
    excerpt: str | None = None  # Optional context around the content
    document_hash: str | None = None  # SHA256:hex of canonical content

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("Evidence.id is required")
        if len(self.source_ids) < 1:
            raise ValueError("Evidence must reference at least one Source")
        if not self.content:
            raise ValueError("Evidence.content is required")

    def with_correction(self, new_content: str, reason: str) -> "Evidence":
        """Create a new Evidence representing a correction.

        The original Evidence is NOT modified (immutability). The new
        Evidence should be linked to the original via a correction Signal
        (see Runtime Model OQ-10).
        """
        return Evidence(
            id=new_id(),
            source_ids=self.source_ids,
            content=new_content,
            quality=self.quality,  # Inherited; can be overridden
            retrievable=True,
            source_type=self.source_type,
            char_offset=self.char_offset,
            excerpt=self.excerpt,
            document_hash=self.document_hash,
        )

    def mark_non_retrievable(self) -> "Evidence":
        """Mark this Evidence as non-retrievable.

        Returns a new Evidence instance with retrievable=False. Used when
        retrieval fails (Workflow Model S2-G4).
        """
        # Since Evidence is frozen, we create a new instance.
        return replace(self, retrievable=False)

    @classmethod
    def create(
        cls,
        source_ids: tuple[ID, ...],
        content: str,
        quality: Quality,
        id: ID | None = None,
        source_type: SourceType | None = None,
        char_offset: tuple[int, int] | None = None,
        excerpt: str | None = None,
        document_hash: str | None = None,
    ) -> "Evidence":
        """Factory method to create new Evidence."""
        return cls(
            id=id if id is not None else new_id(),
            source_ids=source_ids,
            content=content,
            quality=quality,
            source_type=source_type,
            char_offset=char_offset,
            excerpt=excerpt,
            document_hash=document_hash,
        )
