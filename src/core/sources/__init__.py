"""
Source type per Object Model §2.

A Source is an origin of information. Sources are external to the system;
the system observes them. Sources produce Evidence, but are not themselves
Evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum

from src.core.ids import ID, new_id
from src.core.lifecycle import SOURCE_LIFECYCLE, SourceStatus, assert_transition
from src.core.timestamps import now_utc


class SourceType(str, Enum):
    """The kind of source (mirrors Evidence.source_type in Workflow Model)."""

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
class Source:
    """An origin of information.

    The id is immutable (INV-2). Lifecycle transitions (active <-> deactivated
    -> retired) are validated against SOURCE_LIFECYCLE.
    """

    id: ID
    type: SourceType
    url: str
    name: str
    status: SourceStatus = SourceStatus.ACTIVE
    reliability_score: float = 1.0  # 0.0–1.0, default 1.0
    activated_at: str = field(default_factory=now_utc)
    last_observed_at: str | None = None
    health_notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("Source.id is required")
        if not self.url:
            raise ValueError("Source.url is required")
        if not self.name:
            raise ValueError("Source.name is required")
        if not (0.0 <= self.reliability_score <= 1.0):
            raise ValueError(
                f"Source.reliability_score must be in [0.0, 1.0], got {self.reliability_score}"
            )

    def transition(self, new_status: SourceStatus) -> "Source":
        """Transition to a new status. Validates against SOURCE_LIFECYCLE.

        Raises:
            LifecycleError: If the transition is not allowed.
        """
        assert_transition(SOURCE_LIFECYCLE, self.status, new_status)
        return replace(self, status=new_status)

    def deactivate(self) -> "Source":
        """Deactivate the Source."""
        return self.transition(SourceStatus.DEACTIVATED)

    def reactivate(self) -> "Source":
        """Reactivate a deactivated Source."""
        if self.status != SourceStatus.DEACTIVATED:
            raise ValueError(f"Cannot reactivate from {self.status}")
        return self.transition(SourceStatus.ACTIVE)

    def activate(self) -> "Source":
        """Attempt to activate the Source.

        Generic activate: transitions to ACTIVE. Will fail with LifecycleError
        if the current state is RETIRED (terminal). For DEACTIVATED sources,
        use reactivate() (semantically identical but with a precondition check).
        """
        return self.transition(SourceStatus.ACTIVE)

    def retire(self) -> "Source":
        """Retire the Source. Terminal state."""
        if self.status == SourceStatus.RETIRED:
            return self
        return self.transition(SourceStatus.RETIRED)

    def record_observation(self, timestamp: str | None = None) -> "Source":
        """Record that the Source was observed at the given timestamp.

        Returns a new instance with updated last_observed_at.
        """
        ts = timestamp or now_utc()
        return replace(self, last_observed_at=ts)

    def add_health_note(self, note: str) -> "Source":
        """Append a health note."""
        return replace(self, health_notes=self.health_notes + (note,))

    @classmethod
    def create(
        cls,
        type: SourceType,
        url: str,
        name: str,
        id: ID | None = None,
        reliability_score: float = 1.0,
    ) -> "Source":
        """Factory method to create a new Source with auto-generated ID."""
        return cls(
            id=id if id is not None else new_id(),
            type=type,
            url=url,
            name=name,
            reliability_score=reliability_score,
        )
