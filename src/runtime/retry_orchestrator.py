"""
RetryOrchestrator — Phase 3 Checkpoint 4.

The RetryOrchestrator is the consumer of `RetryDecision`s. It wires:
    - `RuntimeCycle` (which produces a CycleReport),
    - `RetryManager` (which produces a RetryDecision),
    - `WorkQueue` (where retry WorkItems are enqueued),
    - `DeadLetterQueue` (where exhausted WorkItems go).

Its single public method, `handle_failed_cycle`, runs:
    1. RetryManager.evaluate(validation, cycle_report, attempt).
    2. If `decision.route_to_dead_letter`: push WorkItem into DLQ.
    3. If `decision.should_retry`: enqueue a fresh WorkItem for the retry.
    4. Return the outcome summary.

The orchestrator does NOT run the retry itself — that is a separate cycle
dispatch. It only enqueues.

Dependency rules:
- Orchestrator depends only on RuntimeCycle, RetryManager, WorkQueue,
  DeadLetterQueue, and the existing `src.runtime` types.
- It MUST NOT import any concrete persistence backend.
- It MUST NOT modify domain lifecycle directly; if it needs to mark a
  WorkItem FAILED, it goes through `WorkQueue.mark_failed`.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.core.ids import new_id
from src.core.timestamps import now_utc
from src.runtime.cycle import RuntimeCycle
from src.runtime.dead_letter import DeadLetterQueue
from src.runtime.queue import (
    WorkItem,
    WorkItemPriority,
    WorkItemStatus,
    WorkQueue,
)
from src.runtime.retry_manager import RetryManager
from src.runtime.validator import ValidationReport


@dataclass(frozen=True, slots=True)
class RetryOutcome:
    """Result of processing a failed cycle."""

    decision_route: str  # "retry" | "dead_letter" | "noop"
    attempt: int
    retry_item_id: str | None = None
    dead_lettered: bool = False
    reason: str = ""


class RetryOrchestrator:
    """Executes RetryDecisions against the queue and DLQ."""

    def __init__(
        self,
        retry_manager: RetryManager,
        queue: WorkQueue,
        dead_letter: DeadLetterQueue,
        runtime_cycle: RuntimeCycle | None = None,
    ) -> None:
        self._retry_manager = retry_manager
        self._queue = queue
        self._dead_letter = dead_letter
        self._runtime_cycle = runtime_cycle

    def handle_failed_cycle(
        self,
        *,
        original_item: WorkItem,
        validation: ValidationReport | None,
        cycle_report: object | None,
        attempt: int,
        retry_priority: WorkItemPriority = WorkItemPriority.NORMAL,
    ) -> RetryOutcome:
        """Decide what to do with a failed cycle, then act on the decision.

        Args:
            original_item: The WorkItem that just failed.
            validation: ValidationReport from the Validator (may be None).
            cycle_report: CycleReport from RuntimeCycle (may be None).
            attempt: The attempt number that just failed.
            retry_priority: Priority to assign to the retry WorkItem.

        Returns:
            A `RetryOutcome` describing what was done.
        """
        decision = self._retry_manager.evaluate(validation, cycle_report, attempt)  # type: ignore[arg-type]

        # Route to DeadLetterQueue first if requested (exhausted/manual).
        if decision.route_to_dead_letter:
            # Mark the original item FAILED so the queue's terminal log
            # reflects the outcome.
            try:
                self._queue.mark_failed(original_item, error=decision.reason)
            except Exception:
                # Item may already be terminal if Workflow already finalized it.
                pass
            added = self._dead_letter.enqueue(
                original_item, reason=decision.reason, attempt=attempt
            )
            return RetryOutcome(
                decision_route="dead_letter",
                attempt=decision.attempt,
                retry_item_id=None,
                dead_lettered=added,
                reason=decision.reason,
            )

        # No retry and no DLQ route → nothing to do (e.g., success path
        # accidentally called here).
        if not decision.should_retry:
            return RetryOutcome(
                decision_route="noop",
                attempt=decision.attempt,
                reason=decision.reason,
            )

        # Schedule the retry by enqueueing a fresh WorkItem with the
        # same cycle_id but a new id and a "retry" trigger tag.
        from dataclasses import replace

        retry_item = WorkItem(
            id=new_id(),
            cycle_id=original_item.cycle_id,
            priority=retry_priority,
            status=WorkItemStatus.PENDING,
            trigger="retry",
            enqueued_at=now_utc(),
        )
        self._queue.enqueue(retry_item)

        return RetryOutcome(
            decision_route="retry",
            attempt=decision.attempt,
            retry_item_id=str(retry_item.id),
            dead_lettered=False,
            reason=decision.reason,
        )

    def handle_replay_from_dead_letter(
        self,
        *,
        retry_priority: WorkItemPriority = WorkItemPriority.NORMAL,
    ) -> RetryOutcome | None:
        """Pop the oldest DLQ entry and re-enqueue it for another attempt.

        Returns the outcome, or None if the DLQ was empty.
        """
        entry = self._dead_letter.pop_oldest()
        if entry is None:
            return None

        retry_item = WorkItem(
            id=new_id(),
            cycle_id=entry.item.cycle_id,
            priority=retry_priority,
            status=WorkItemStatus.PENDING,
            trigger="replay",
            enqueued_at=now_utc(),
        )
        self._queue.enqueue(retry_item)
        return RetryOutcome(
            decision_route="retry",
            attempt=entry.attempt,
            retry_item_id=str(retry_item.id),
            dead_lettered=False,
            reason=f"replayed from DLQ: {entry.reason}",
        )


__all__ = ["RetryOrchestrator", "RetryOutcome"]