"""Tests for the Source type."""

import pytest

from src.core.lifecycle import LifecycleError
from src.core.sources import Source, SourceStatus, SourceType


class TestSourceCreate:
    def test_minimal_creation(self) -> None:
        source = Source.create(
            type=SourceType.NEWS_ARTICLE,
            url="https://reuters.com/article/123",
            name="Reuters",
        )
        assert source.id
        assert source.type == SourceType.NEWS_ARTICLE
        assert source.url == "https://reuters.com/article/123"
        assert source.name == "Reuters"
        assert source.status == SourceStatus.ACTIVE
        assert source.reliability_score == 1.0

    def test_with_reliability_score(self) -> None:
        source = Source.create(
            type=SourceType.NEWS_ARTICLE,
            url="https://example.com",
            name="Example",
            reliability_score=0.75,
        )
        assert source.reliability_score == 0.75


class TestSourceValidation:
    def test_invalid_reliability_below_zero(self) -> None:
        with pytest.raises(ValueError):
            Source.create(
                type=SourceType.NEWS_ARTICLE,
                url="https://x.com",
                name="X",
                reliability_score=-0.1,
            )

    def test_invalid_reliability_above_one(self) -> None:
        with pytest.raises(ValueError):
            Source.create(
                type=SourceType.NEWS_ARTICLE,
                url="https://x.com",
                name="X",
                reliability_score=1.1,
            )

    def test_empty_url_rejected(self) -> None:
        with pytest.raises(ValueError):
            Source.create(type=SourceType.NEWS_ARTICLE, url="", name="X")

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ValueError):
            Source.create(type=SourceType.NEWS_ARTICLE, url="https://x.com", name="")


class TestSourceLifecycle:
    def test_active_to_deactivated(self) -> None:
        source = Source.create(type=SourceType.NEWS_ARTICLE, url="https://x.com", name="X")
        deactivated = source.deactivate()
        assert deactivated.status == SourceStatus.DEACTIVATED

    def test_deactivated_to_active(self) -> None:
        source = Source.create(type=SourceType.NEWS_ARTICLE, url="https://x.com", name="X")
        deactivated = source.deactivate()
        reactivated = deactivated.reactivate()
        assert reactivated.status == SourceStatus.ACTIVE

    def test_active_to_retired(self) -> None:
        source = Source.create(type=SourceType.NEWS_ARTICLE, url="https://x.com", name="X")
        retired = source.retire()
        assert retired.status == SourceStatus.RETIRED

    def test_retire_idempotent(self) -> None:
        source = Source.create(type=SourceType.NEWS_ARTICLE, url="https://x.com", name="X")
        retired = source.retire()
        retired_again = retired.retire()
        assert retired_again.status == SourceStatus.RETIRED

    def test_invalid_transition_raises(self) -> None:
        source = Source.create(type=SourceType.NEWS_ARTICLE, url="https://x.com", name="X")
        retired = source.retire()
        with pytest.raises(LifecycleError):
            retired.activate()  # Can't go from RETIRED to ACTIVE


class TestSourceObservation:
    def test_record_observation(self) -> None:
        source = Source.create(type=SourceType.NEWS_ARTICLE, url="https://x.com", name="X")
        recorded = source.record_observation()
        assert recorded.last_observed_at is not None

    def test_add_health_note(self) -> None:
        source = Source.create(type=SourceType.NEWS_ARTICLE, url="https://x.com", name="X")
        noted = source.add_health_note("Slow response 2026-07-15")
        assert "Slow response 2026-07-15" in noted.health_notes

    def test_multiple_health_notes_appended(self) -> None:
        source = Source.create(type=SourceType.NEWS_ARTICLE, url="https://x.com", name="X")
        s = source.add_health_note("Note 1").add_health_note("Note 2")
        assert len(s.health_notes) == 2


class TestSourceImmutability:
    def test_cannot_modify_id(self) -> None:
        source = Source.create(type=SourceType.NEWS_ARTICLE, url="https://x.com", name="X")
        with pytest.raises(Exception):
            source.id = "new_id"  # type: ignore[misc]
