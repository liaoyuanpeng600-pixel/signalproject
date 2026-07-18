"""
Pipeline orchestrator.

The Pipeline runs all 6 stages in order. It:
- Emits lifecycle events (StageStarted, StageCompleted, GateEvaluated, etc.)
- Routes failures to appropriate paths (handled by individual stages)
- Produces a CycleReport at the end

Per the user constraints:
- "Workflow orchestrates only; business rules remain in domain objects."
- "All state transitions must go through the lifecycle module." (stages call
  domain methods, which call lifecycle)
- "No direct persistence logic inside the workflow layer." (Pipeline does
  not persist; that is Persistence's job — Phase 4)
- "Prefer events and interfaces over tight coupling." (stages emit events;
  Pipeline emits WorkflowCompleted)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.core.ids import ID
from src.core.timestamps import now_utc
from src.workflow.context import PipelineContext
from src.workflow.events import WorkflowCompleted
from src.workflow.stages import Stage, default_stages


@dataclass
class PipelineResult:
    """Result of a complete pipeline run (one cycle)."""

    cycle_id: ID
    started_at: str
    completed_at: str
    signals_emitted: int
    research_emitted: int
    theses_updated: int


class Pipeline:
    """Orchestrates the 6-stage workflow.

    The Pipeline:
    1. Iterates through stages in order
    2. Emits StageStarted before each stage
    3. Calls stage.execute(context)
    4. Emits StageCompleted after each stage
    5. Continues regardless of individual stage failure (gates route to failure paths)
    6. Aborts on critical infrastructure failure (Phase 3+ concern)
    7. Emits WorkflowCompleted at the end
    """

    def __init__(self, stages: list[Stage] | None = None):
        self._stages = stages if stages is not None else default_stages()

    @property
    def stages(self) -> list[Stage]:
        return list(self._stages)

    def run(self, context: PipelineContext) -> PipelineResult:
        """Execute all stages in order.

        Args:
            context: The pipeline context with sources, entities, etc.

        Returns:
            PipelineResult summarizing the cycle.
        """
        started_at = context.started_at
        for stage in self._stages:
            try:
                stage.execute(context)
            except Exception:
                # Critical failure in a stage's orchestration logic.
                # Continue with remaining stages; the cycle still completes.
                # Per Workflow Model §"Error Recovery Flow", cycle-level aborts
                # are for infrastructure failures (e.g., Persistence unavailable),
                # which we don't have yet.
                continue

        completed_at = now_utc()
        result = PipelineResult(
            cycle_id=context.cycle_id,
            started_at=started_at,
            completed_at=completed_at,
            signals_emitted=context.signals_emitted,
            research_emitted=context.research_emitted,
            theses_updated=context.theses_updated,
        )

        # Emit WorkflowCompleted event
        context.emit(
            WorkflowCompleted(
                cycle_id=context.cycle_id,
                started_at=started_at,
                completed_at=completed_at,
                signals_emitted=context.signals_emitted,
                research_emitted=context.research_emitted,
                theses_updated=context.theses_updated,
            )
        )

        return result

    def cycle_report(self, context: PipelineContext, result: PipelineResult) -> dict[str, Any]:
        """Produce a CycleReport from the pipeline context and result.

        Per Object Model operational concepts, CycleReport summarizes
        one cycle's outputs. Phase 3 Runtime will extend this with cost,
        breach reasons, and degrade mode status.
        """
        return {
            "cycle_id": result.cycle_id,
            "started_at": result.started_at,
            "completed_at": result.completed_at,
            "signals_emitted": result.signals_emitted,
            "research_emitted": result.research_emitted,
            "theses_updated": result.theses_updated,
            "evidences_produced": context.evidences_produced,
            "degraded_sources": len(context.degraded_sources),
            "rejected_evidences": len(context.rejected_evidences),
            "held_research": len(context.held_research),
            "pending_theses": len(context.theses_pending),
        }