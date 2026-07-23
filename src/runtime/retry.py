"""
Retry Policy and Decision — Phase 3 Checkpoint 4.

This module defines:
- `RetryPolicyKind`: enum of canonical policy families (MANUAL, IMMEDIATE,
  EXPONENTIAL).
- `RetryPolicy`: configurable policy (max_attempts, base/max delay).
- `RetryDecision`: pure result returned by policy evaluation. It is
  intentionally separated from execution: the decision says WHAT to do,
  the RetryManager/Orchestrator decides HOW/WHEN to do it.

The RetryPolicy contains NO business rules. It does not know which gate
failures are retryable — that determination is delegated to the caller
(via the `RetryContext` parameter to `RetryManager.evaluate`). Business
rules ("S3-G2 is retryable, S3-G3 is not") live with the workflow gates,
not the runtime.

Dependency rules:
- This module MUST NOT import any concrete persistence backend.
- This module MUST NOT import workflow gates.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RetryPolicyKind(str, Enum):
    """Canonical retry policy families."""

    MANUAL = "manual"
    IMMEDIATE = "immediate"
    EXPONENTIAL = "exponential"


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Configurable retry policy.

    Fields:
        kind: Which policy family to use.
        max_attempts: Total attempts including the original cycle. A value
            of 1 means "no retries" (the original attempt is the only one).
        base_delay_seconds: For EXPONENTIAL: initial delay before retry N.
            For IMMEDIATE: ignored (delay is always 0).
        max_delay_seconds: For EXPONENTIAL: cap on computed delay.
        jitter: For EXPONENTIAL: optional multiplicative jitter in [0, 1].
            0.0 = no jitter (deterministic). 0.25 = up to ±25% jitter.

    Raises:
        ValueError: If `max_attempts < 1`, or if EXPONENTIAL params are invalid.
    """

    kind: RetryPolicyKind = RetryPolicyKind.EXPONENTIAL
    max_attempts: int = 3
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 60.0
    jitter: float = 0.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError(f"max_attempts must be >= 1, got {self.max_attempts}")
        if self.base_delay_seconds < 0:
            raise ValueError(f"base_delay_seconds must be >= 0, got {self.base_delay_seconds}")
        if self.max_delay_seconds < self.base_delay_seconds:
            raise ValueError(
                f"max_delay_seconds ({self.max_delay_seconds}) must be >= "
                f"base_delay_seconds ({self.base_delay_seconds})"
            )
        if not (0.0 <= self.jitter <= 1.0):
            raise ValueError(f"jitter must be in [0.0, 1.0], got {self.jitter}")


@dataclass(frozen=True, slots=True)
class RetryDecision:
    """Result of evaluating a retry policy against a failed cycle.

    Fields:
        should_retry: True iff the cycle should be retried (and the policy
            authorizes it).
        attempt: The next attempt number. 1 = original; 2 = first retry; etc.
        delay_seconds: How long to wait before the retry (0 for IMMEDIATE).
        route_to_dead_letter: True iff the failed cycle should be sent to
            the DeadLetterQueue instead of (or in addition to) being retried.
        reason: Human-readable explanation of the decision.
        policy_kind: The policy family that produced this decision.
    """

    should_retry: bool
    attempt: int
    delay_seconds: float
    route_to_dead_letter: bool
    reason: str
    policy_kind: RetryPolicyKind

    @classmethod
    def no_retry(
        cls, *, reason: str, policy_kind: RetryPolicyKind
    ) -> "RetryDecision":
        """Factory for a decision that declines to retry."""
        return cls(
            should_retry=False,
            attempt=1,
            delay_seconds=0.0,
            route_to_dead_letter=False,
            reason=reason,
            policy_kind=policy_kind,
        )

    @classmethod
    def retry(
        cls,
        *,
        attempt: int,
        delay_seconds: float,
        policy_kind: RetryPolicyKind,
        reason: str = "",
    ) -> "RetryDecision":
        """Factory for a retry decision."""
        return cls(
            should_retry=True,
            attempt=attempt,
            delay_seconds=delay_seconds,
            route_to_dead_letter=False,
            reason=reason or f"retry attempt {attempt} per {policy_kind.value}",
            policy_kind=policy_kind,
        )

    @classmethod
    def dead_letter(
        cls,
        *,
        attempt: int,
        reason: str,
        policy_kind: RetryPolicyKind,
    ) -> "RetryDecision":
        """Factory for a decision that routes the failed cycle to the DLQ."""
        return cls(
            should_retry=False,
            attempt=attempt,
            delay_seconds=0.0,
            route_to_dead_letter=True,
            reason=reason,
            policy_kind=policy_kind,
        )


__all__ = ["RetryDecision", "RetryPolicy", "RetryPolicyKind"]