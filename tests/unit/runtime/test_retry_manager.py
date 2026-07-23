"""Tests for RetryManager (Runtime Checkpoint 4)."""

from typing import Any

import pytest

from src.core.ids import new_id
from src.runtime.cycle import CycleReport
from src.runtime.queue import WorkItem, WorkItemPriority, WorkItemStatus
from src.runtime.retry import RetryDecision, RetryPolicy, RetryPolicyKind
from src.runtime.retry_manager import RetryContext, RetryManager
from src.runtime.validator import StageValidation, ValidationReport


def _cycle_report(error: str | None = None) -> CycleReport:
    return CycleReport(
        cycle_id=new_id(),
        started_at="2026-07-19T00:00:00Z",
        completed_at="2026-07-19T00:00:01Z",
        signals_emitted=0,
        research_emitted=0,
        theses_updated=0,
        sources_loaded=0,
        entities_loaded=0,
        validation_passed=False,
        gates_total=2,
        gates_passed=1,
        gates_failed=1,
        signals_persisted=0,
        research_persisted=0,
        theses_persisted=0,
        error=error,
    )


def _validation(passed: bool = False) -> ValidationReport:
    sv = StageValidation(
        stage_name="S1",
        gate_count=2,
        passed_count=1 if passed else 0,
        failed_count=0 if passed else 1,
        first_failure=None if passed else ("S1-G1", "no candidates"),
        evaluations=(("S1-G1", passed, None if passed else "no candidates"),),
    )
    return ValidationReport(
        cycle_id="cycle-1",
        stage_validations=(sv,),
        total_gates=2,
        total_passed=1 if passed else 0,
        total_failed=0 if passed else 1,
    )


# ----------------------- MANUAL policy -----------------------


class TestManualPolicy:
    def test_manual_always_dlqs(self) -> None:
        mgr = RetryManager(RetryPolicy(kind=RetryPolicyKind.MANUAL, max_attempts=5))
        d = mgr.evaluate(_validation(), _cycle_report(), attempt=1)
        assert d.route_to_dead_letter is True
        assert d.should_retry is False
        assert "manual" in d.reason

    def test_manual_with_infrastructure_failure(self) -> None:
        mgr = RetryManager(RetryPolicy(kind=RetryPolicyKind.MANUAL))
        d = mgr.evaluate(
            _validation(),
            _cycle_report(error="kaboom"),
            attempt=1,
        )
        assert d.route_to_dead_letter is True
        assert "kaboom" in d.reason


# ----------------------- IMMEDIATE policy -----------------------


class TestImmediatePolicy:
    def test_first_attempt_retries(self) -> None:
        mgr = RetryManager(
            RetryPolicy(kind=RetryPolicyKind.IMMEDIATE, max_attempts=3)
        )
        d = mgr.evaluate(_validation(), _cycle_report(), attempt=1)
        assert d.should_retry is True
        assert d.route_to_dead_letter is False
        assert d.delay_seconds == 0.0
        assert d.attempt == 2

    def test_budget_exhausted_routes_to_dlq(self) -> None:
        mgr = RetryManager(
            RetryPolicy(kind=RetryPolicyKind.IMMEDIATE, max_attempts=3)
        )
        # attempt=3 (== max_attempts) → budget exhausted
        d = mgr.evaluate(_validation(), _cycle_report(), attempt=3)
        assert d.route_to_dead_letter is True
        assert "budget exhausted" in d.reason

    def test_within_budget_keeps_retrying(self) -> None:
        mgr = RetryManager(
            RetryPolicy(kind=RetryPolicyKind.IMMEDIATE, max_attempts=5)
        )
        d = mgr.evaluate(_validation(), _cycle_report(), attempt=4)
        assert d.should_retry is True
        assert d.attempt == 5


# ----------------------- EXPONENTIAL policy -----------------------


class TestExponentialPolicy:
    def test_first_retry_uses_base_delay(self) -> None:
        mgr = RetryManager(
            RetryPolicy(
                kind=RetryPolicyKind.EXPONENTIAL,
                max_attempts=5,
                base_delay_seconds=2.0,
                max_delay_seconds=60.0,
            )
        )
        d = mgr.evaluate(_validation(), _cycle_report(), attempt=1)
        assert d.should_retry is True
        assert d.delay_seconds == pytest.approx(2.0)
        assert d.attempt == 2

    def test_second_retry_doubles_delay(self) -> None:
        mgr = RetryManager(
            RetryPolicy(
                kind=RetryPolicyKind.EXPONENTIAL,
                max_attempts=5,
                base_delay_seconds=2.0,
            )
        )
        d = mgr.evaluate(_validation(), _cycle_report(), attempt=2)
        assert d.delay_seconds == pytest.approx(4.0)
        assert d.attempt == 3

    def test_third_retry_quadruples_delay(self) -> None:
        # Standard exponential backoff: delay = base * 2^(attempt-1)
        # attempt=1 -> 1*base, attempt=2 -> 2*base, attempt=3 -> 4*base.
        mgr = RetryManager(
            RetryPolicy(
                kind=RetryPolicyKind.EXPONENTIAL,
                max_attempts=10,
                base_delay_seconds=1.0,
            )
        )
        d = mgr.evaluate(_validation(), _cycle_report(), attempt=3)
        assert d.delay_seconds == pytest.approx(4.0)
        assert d.attempt == 4

    def test_delay_capped_at_max(self) -> None:
        mgr = RetryManager(
            RetryPolicy(
                kind=RetryPolicyKind.EXPONENTIAL,
                max_attempts=10,
                base_delay_seconds=1.0,
                max_delay_seconds=10.0,
            )
        )
        d = mgr.evaluate(_validation(), _cycle_report(), attempt=6)
        # 2 ** 4 = 16, capped at 10.
        assert d.delay_seconds == pytest.approx(10.0)

    def test_jitter_with_zero_clock_returns_base(self) -> None:
        # When current_time=0 (default), jitter is no-op.
        mgr = RetryManager(
            policy=RetryPolicy(
                kind=RetryPolicyKind.EXPONENTIAL,
                max_attempts=3,
                base_delay_seconds=2.0,
                jitter=0.5,
            ),
            context=RetryContext(current_time=0.0),
        )
        d = mgr.evaluate(_validation(), _cycle_report(), attempt=1)
        assert d.delay_seconds == pytest.approx(2.0)

    def test_jitter_with_nonzero_clock_modifies_delay(self) -> None:
        mgr = RetryManager(
            policy=RetryPolicy(
                kind=RetryPolicyKind.EXPONENTIAL,
                max_attempts=3,
                base_delay_seconds=10.0,
                jitter=0.5,
            ),
            context=RetryContext(current_time=12345.678),
        )
        d = mgr.evaluate(_validation(), _cycle_report(), attempt=1)
        # With jitter=0.5, delay is in [5.0, 15.0].
        assert 5.0 <= d.delay_seconds <= 15.0


# ----------------------- caller-controlled non-retryability -----------------------


class TestCallerOverride:
    def test_non_retryable_routes_to_dlq(self) -> None:
        mgr = RetryManager(
            policy=RetryPolicy(kind=RetryPolicyKind.IMMEDIATE, max_attempts=5),
            context=RetryContext(is_retryable=False),
        )
        d = mgr.evaluate(_validation(), _cycle_report(), attempt=1)
        assert d.route_to_dead_letter is True
        assert d.should_retry is False

    def test_infrastructure_failure_always_dlqs(self) -> None:
        """Even if max_attempts is large and policy is EXPONENTIAL, an
        infrastructure failure must route to DLQ — the cycle never reached
        gates, so retrying won't help.
        """
        mgr = RetryManager(
            RetryPolicy(kind=RetryPolicyKind.EXPONENTIAL, max_attempts=10)
        )
        d = mgr.evaluate(
            _validation(),
            _cycle_report(error="store unreachable"),
            attempt=1,
        )
        assert d.route_to_dead_letter is True
        assert "store unreachable" in d.reason

    def test_null_validation_and_cycle_report(self) -> None:
        """Defensive: handle None inputs gracefully (catastrophic abort)."""
        mgr = RetryManager(RetryPolicy(kind=RetryPolicyKind.IMMEDIATE))
        d = mgr.evaluate(None, None, attempt=1)
        # No error means "not a cycle-level abort" → policy applies normally.
        # With IMMEDIATE and max_attempts=3, attempt=1 should retry.
        assert d.should_retry is True


# ----------------------- dep-inversion / no business rules -----------------------


class TestRetryManagerNoBusinessLogic:
    def test_no_workflow_gate_imports(self) -> None:
        """RetryManager must not import workflow gates (no business rules)."""
        import re

        for module_name in (
            "src.runtime.retry_manager",
            "src.runtime.retry",
            "src.runtime.retry_orchestrator",
            "src.runtime.dead_letter",
        ):
            import importlib

            mod = importlib.import_module(module_name)
            source_path = mod.__file__ or ""
            with open(source_path, encoding="utf-8") as f:
                contents = f.read()
            # No imports from workflow.* gates
            assert "from src.workflow.gates" not in contents, module_name
            assert "from src.workflow.stages" not in contents, module_name
            # No imports of concrete persistence backends.
            import_re = re.compile(
                r"^\s*(?:from\s+src\.persistence\.in_memory|import\s+src\.persistence\.in_memory)",
                re.MULTILINE,
            )
            assert not import_re.search(contents), module_name