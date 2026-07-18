"""Tests for the lifecycle module (INV-6)."""

import pytest

from src.core.lifecycle import (
    LifecycleError,
    RESEARCH_LIFECYCLE,
    SIGNAL_LIFECYCLE,
    SOURCE_LIFECYCLE,
    THESIS_LIFECYCLE,
    ResearchStatus,
    SignalStatus,
    SourceStatus,
    ThesisStatus,
    assert_transition,
    can_transition,
    terminal_states,
)


class TestSignalLifecycle:
    def test_draft_to_verified(self) -> None:
        assert can_transition(SIGNAL_LIFECYCLE, SignalStatus.DRAFT, SignalStatus.VERIFIED)

    def test_draft_to_rejected(self) -> None:
        assert can_transition(SIGNAL_LIFECYCLE, SignalStatus.DRAFT, SignalStatus.REJECTED)

    def test_verified_to_active(self) -> None:
        assert can_transition(SIGNAL_LIFECYCLE, SignalStatus.VERIFIED, SignalStatus.ACTIVE)

    def test_active_to_decayed(self) -> None:
        assert can_transition(SIGNAL_LIFECYCLE, SignalStatus.ACTIVE, SignalStatus.DECAYED)

    def test_active_to_superseded(self) -> None:
        assert can_transition(SIGNAL_LIFECYCLE, SignalStatus.ACTIVE, SignalStatus.SUPERSEDED)

    def test_held_to_active(self) -> None:
        assert can_transition(SIGNAL_LIFECYCLE, SignalStatus.HELD, SignalStatus.ACTIVE)

    def test_draft_to_active_forbidden(self) -> None:
        # Must go through VERIFIED first.
        assert not can_transition(SIGNAL_LIFECYCLE, SignalStatus.DRAFT, SignalStatus.ACTIVE)

    def test_verified_to_active_works(self) -> None:
        # Allow direct verified -> active (no held intermediate).
        assert can_transition(SIGNAL_LIFECYCLE, SignalStatus.VERIFIED, SignalStatus.ACTIVE)

    def test_active_to_held_forbidden(self) -> None:
        # Cannot re-hold an active signal.
        assert not can_transition(SIGNAL_LIFECYCLE, SignalStatus.ACTIVE, SignalStatus.HELD)

    def test_terminal_states(self) -> None:
        terminals = terminal_states(SIGNAL_LIFECYCLE)
        assert terminals == frozenset(
            {SignalStatus.REJECTED, SignalStatus.DECAYED, SignalStatus.SUPERSEDED}
        )

    def test_assert_transition_raises_on_invalid(self) -> None:
        with pytest.raises(LifecycleError):
            assert_transition(SIGNAL_LIFECYCLE, SignalStatus.DRAFT, SignalStatus.ACTIVE)


class TestThesisLifecycle:
    def test_emerging_to_evolving(self) -> None:
        assert can_transition(THESIS_LIFECYCLE, ThesisStatus.EMERGING, ThesisStatus.EVOLVING)

    def test_evolving_to_mature(self) -> None:
        assert can_transition(THESIS_LIFECYCLE, ThesisStatus.EVOLVING, ThesisStatus.MATURE)

    def test_mature_to_evolving_reopen(self) -> None:
        # A mature Thesis can be reopened by evolving it again.
        assert can_transition(THESIS_LIFECYCLE, ThesisStatus.MATURE, ThesisStatus.EVOLVING)

    def test_mature_to_supersede(self) -> None:
        assert can_transition(THESIS_LIFECYCLE, ThesisStatus.MATURE, ThesisStatus.SUPERSEDED)

    def test_terminal_states(self) -> None:
        terminals = terminal_states(THESIS_LIFECYCLE)
        assert terminals == frozenset({ThesisStatus.SUPERSEDED, ThesisStatus.RETIRED})


class TestResearchLifecycle:
    def test_open_to_ongoing(self) -> None:
        assert can_transition(RESEARCH_LIFECYCLE, ResearchStatus.OPEN, ResearchStatus.ONGOING)

    def test_open_to_concluded_direct(self) -> None:
        # Quick conclusion allowed.
        assert can_transition(RESEARCH_LIFECYCLE, ResearchStatus.OPEN, ResearchStatus.CONCLUDED)

    def test_ongoing_to_concluded(self) -> None:
        assert can_transition(RESEARCH_LIFECYCLE, ResearchStatus.ONGOING, ResearchStatus.CONCLUDED)

    def test_paused_to_ongoing(self) -> None:
        assert can_transition(RESEARCH_LIFECYCLE, ResearchStatus.PAUSED, ResearchStatus.ONGOING)

    def test_concluded_is_terminal(self) -> None:
        terminals = terminal_states(RESEARCH_LIFECYCLE)
        assert terminals == frozenset({ResearchStatus.CONCLUDED})


class TestSourceLifecycle:
    def test_active_to_deactivated(self) -> None:
        assert can_transition(SOURCE_LIFECYCLE, SourceStatus.ACTIVE, SourceStatus.DEACTIVATED)

    def test_deactivated_to_active(self) -> None:
        assert can_transition(SOURCE_LIFECYCLE, SourceStatus.DEACTIVATED, SourceStatus.ACTIVE)

    def test_active_to_retired(self) -> None:
        assert can_transition(SOURCE_LIFECYCLE, SourceStatus.ACTIVE, SourceStatus.RETIRED)

    def test_terminal_states(self) -> None:
        terminals = terminal_states(SOURCE_LIFECYCLE)
        assert terminals == frozenset({SourceStatus.RETIRED})

    def test_assert_transition_raises_on_invalid(self) -> None:
        with pytest.raises(LifecycleError):
            assert_transition(SOURCE_LIFECYCLE, SourceStatus.RETIRED, SourceStatus.ACTIVE)
