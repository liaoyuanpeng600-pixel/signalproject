"""
RetryManager — Phase 3 Checkpoint 4.

The RetryManager evaluates a retry policy against a failed cycle and emits
a `RetryDecision`. It is a pure orchestrator: it does NOT execute the retry
itself; the caller (RetryOrchestrator) does that.

Inputs:
- A `RetryPolicy` (configuration).
- A `ValidationReport` (gate-evaluation outcome).
- A `CycleReport` (cycle-level outcome: signals, errors, etc.).
- The current `attempt` number (1 = original cycle).
- A `RetryContext` carrying the optional store-binding handle (for policies
  that may consult durable state in the future).

Outputs:
- A `RetryDecision` describing what to do next.

Business rules are NOT in this module. The manager asks the caller
("is this cycle retryable?") via a single hook — `RetryContext.is_retryable`.
Defaults to True; production wiring overrides per gate.

Dependency rules:
- RetryManager MUST NOT import any concrete persistence backend.
- RetryManager MUST NOT import workflow gates (no business rules).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from src.runtime.retry import RetryDecision, RetryPolicy, RetryPolicyKind

if TYPE_CHECKING:
    from src.runtime.cycle import CycleReport
    from src.runtime.validator import ValidationReport


@dataclass
class RetryContext:
    """Context passed to the RetryManager on each evaluation.

    `is_retryable` is a hook the caller supplies. It encodes business rules
    (e.g., "S3-G3 failures are not retryable"). The default returns True.
    `clock` allows tests to inject deterministic time for EXPONENTIAL.
    """

    is_retryable: bool = True
    current_time: float = 0.0  # monotonic seconds; tests inject this


class RetryManager:
    """Evaluates retry decisions for failed cycles.

    The manager is stateless except for its policy and clock. It does not
    mutate the inputs.
    """

    def __init__(
        self,
        policy: RetryPolicy,
        *,
        context: RetryContext | None = None,
    ) -> None:
        self._policy = policy
        self._context = context or RetryContext()

    @property
    def policy(self) -> RetryPolicy:
        return self._policy

    def evaluate(
        self,
        validation: "ValidationReport | None",
        cycle_report: "CycleReport | None",
        attempt: int,
    ) -> RetryDecision:
        """Evaluate the retry decision.

        Args:
            validation: Gate-evaluation report from the Validator. May be
                None if the cycle aborted before validation ran.
            cycle_report: CycleReport from RuntimeCycle. May be None if the
                cycle aborted catastrophically.
            attempt: The attempt number that just failed. 1 = original;
                2 = first retry; etc.

        Returns:
            A `RetryDecision` describing the next action.

        Decision logic:
            1. If the cycle_report.error is set (infrastructure failure),
               route to DLQ immediately — the cycle didn't reach gates.
            2. If the caller marks the failure as non-retryable (e.g., a
               business rule), route to DLQ.
            3. If `attempt >= policy.max_attempts`, route to DLQ.
            4. Otherwise, produce a retry decision per policy kind.
        """
        # Step 1: Infrastructure failure — cycle never reached gates.
        if cycle_report is not None and cycle_report.error is not None:
            return RetryDecision.dead_letter(
                attempt=attempt,
                reason=f"infrastructure failure: {cycle_report.error}",
                policy_kind=self._policy.kind,
            )

        # Step 2: Caller-marked non-retryable.
        if not self._context.is_retryable:
            return RetryDecision.dead_letter(
                attempt=attempt,
                reason="caller marked failure as non-retryable",
                policy_kind=self._policy.kind,
            )

        # Step 3: Budget exhausted.
        if attempt >= self._policy.max_attempts:
            return RetryDecision.dead_letter(
                attempt=attempt,
                reason=(
                    f"retry budget exhausted: attempt {attempt} >= "
                    f"max_attempts {self._policy.max_attempts}"
                ),
                policy_kind=self._policy.kind,
            )

        # Step 4: Per-policy retry decision.
        next_attempt = attempt + 1
        if self._policy.kind == RetryPolicyKind.MANUAL:
            return RetryDecision.dead_letter(
                attempt=next_attempt,
                reason="manual policy: requires operator intervention",
                policy_kind=self._policy.kind,
            )

        if self._policy.kind == RetryPolicyKind.IMMEDIATE:
            return RetryDecision.retry(
                attempt=next_attempt,
                delay_seconds=0.0,
                policy_kind=self._policy.kind,
                reason=f"immediate retry attempt {next_attempt}",
            )

        # EXPONENTIAL
        delay = self._compute_exponential_delay(next_attempt)
        return RetryDecision.retry(
            attempt=next_attempt,
            delay_seconds=delay,
            policy_kind=self._policy.kind,
            reason=f"exponential backoff retry attempt {next_attempt}",
        )

    def _compute_exponential_delay(self, next_attempt: int) -> float:
        """Compute exponential-backoff delay for the given attempt number.

        Formula: base * 2 ** (attempt - 2), capped at max_delay_seconds,
        with optional ±jitter.

        `next_attempt=2` (first retry) gives `base * 1`. `next_attempt=3`
        gives `base * 2`. `next_attempt=N` gives `base * 2 ** (N-2)`.
        """
        exponent = max(0, next_attempt - 2)
        raw = self._policy.base_delay_seconds * (2 ** exponent)
        capped = min(raw, self._policy.max_delay_seconds)
        if self._policy.jitter > 0.0 and self._context.current_time > 0:
            # Deterministic jitter from clock so tests are reproducible:
            # jitter_offset in [-jitter, +jitter] proportional to fractional clock.
            import math

            frac = (self._context.current_time * 0.0001) % 1.0
            jitter_factor = (frac * 2.0 - 1.0) * self._policy.jitter
            capped = capped * (1.0 + jitter_factor)
        return capped


__all__ = ["RetryContext", "RetryManager"]