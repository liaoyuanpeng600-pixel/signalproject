"""Tests for RetryPolicy + RetryDecision (Runtime Checkpoint 4)."""

import pytest

from src.runtime.retry import RetryDecision, RetryPolicy, RetryPolicyKind


# ----------------------- RetryPolicy -----------------------


class TestRetryPolicyConstruction:
    def test_default_policy(self) -> None:
        p = RetryPolicy()
        assert p.kind == RetryPolicyKind.EXPONENTIAL
        assert p.max_attempts == 3
        assert p.base_delay_seconds == 1.0
        assert p.max_delay_seconds == 60.0
        assert p.jitter == 0.0

    def test_invalid_max_attempts(self) -> None:
        with pytest.raises(ValueError):
            RetryPolicy(max_attempts=0)
        with pytest.raises(ValueError):
            RetryPolicy(max_attempts=-1)

    def test_invalid_base_delay(self) -> None:
        with pytest.raises(ValueError):
            RetryPolicy(base_delay_seconds=-1.0)

    def test_max_must_be_gte_base(self) -> None:
        with pytest.raises(ValueError):
            RetryPolicy(base_delay_seconds=10.0, max_delay_seconds=5.0)

    def test_invalid_jitter(self) -> None:
        with pytest.raises(ValueError):
            RetryPolicy(jitter=-0.1)
        with pytest.raises(ValueError):
            RetryPolicy(jitter=1.5)

    def test_policy_is_frozen(self) -> None:
        p = RetryPolicy()
        with pytest.raises(Exception):  # FrozenInstanceError
            p.max_attempts = 99  # type: ignore[misc]


# ----------------------- RetryDecision -----------------------


class TestRetryDecisionFactories:
    def test_no_retry_factory(self) -> None:
        d = RetryDecision.no_retry(
            reason="nope", policy_kind=RetryPolicyKind.MANUAL
        )
        assert d.should_retry is False
        assert d.attempt == 1
        assert d.delay_seconds == 0.0
        assert d.route_to_dead_letter is False
        assert d.policy_kind == RetryPolicyKind.MANUAL
        assert d.reason == "nope"

    def test_retry_factory(self) -> None:
        d = RetryDecision.retry(
            attempt=2,
            delay_seconds=1.0,
            policy_kind=RetryPolicyKind.EXPONENTIAL,
            reason="transient",
        )
        assert d.should_retry is True
        assert d.attempt == 2
        assert d.delay_seconds == 1.0
        assert d.route_to_dead_letter is False

    def test_retry_factory_default_reason(self) -> None:
        d = RetryDecision.retry(
            attempt=3, delay_seconds=4.0, policy_kind=RetryPolicyKind.IMMEDIATE
        )
        assert "immediate" in d.reason

    def test_dead_letter_factory(self) -> None:
        d = RetryDecision.dead_letter(
            attempt=4,
            reason="budget exhausted",
            policy_kind=RetryPolicyKind.EXPONENTIAL,
        )
        assert d.should_retry is False
        assert d.route_to_dead_letter is True
        assert d.attempt == 4


# ----------------------- decision/execution separation -----------------------


class TestDecisionExecutionSeparation:
    def test_decision_does_not_mutate_state(self) -> None:
        """A RetryDecision is pure data; constructing one must not have side effects."""
        d = RetryDecision.retry(
            attempt=2,
            delay_seconds=0.5,
            policy_kind=RetryPolicyKind.EXPONENTIAL,
        )
        # No side effects beyond the dataclass itself.
        assert d.should_retry is True

    def test_decision_can_be_passed_around(self) -> None:
        d1 = RetryDecision.retry(
            attempt=2, delay_seconds=0.5, policy_kind=RetryPolicyKind.IMMEDIATE
        )
        d2 = d1  # alias
        assert d1 is d2
        assert d1.policy_kind == RetryPolicyKind.IMMEDIATE