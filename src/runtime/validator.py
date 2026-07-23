"""
Runtime Validator — Phase 3 Checkpoint 3.

The Validator orchestrates gate evaluation across all stages of a Pipeline.
It is the gate-evaluation HALF of the Runtime/Workflow split:

    Pipeline    -> executes stages (produces context mutations)
    Validator   -> evaluates gates (verifies context against rules)
    Stage       -> owns its own gates (per Workflow Model)

The Validator contains NO business logic. It does NOT inspect Objects, does
NOT decide failure paths (those are gate properties), and does NOT mutate
the context beyond emitting `GateEvaluated` events via the stages. Its sole
responsibility is to:

  1. Iterate stages in pipeline order.
  2. For each stage, ask the stage to run its gates.
  3. Collect (gate, result) pairs into a `ValidationReport`.
  4. Provide aggregate pass/fail counts and stage summaries.

The Runtime layer composes the Validator with the Pipeline and an Executor.
This keeps Runtime thin: orchestration + persistence I/O, no domain logic.

Dependency rules:
- Validator depends on `workflow.context.PipelineContext`,
  `workflow.pipeline.Pipeline`, `workflow.stages.Stage`, and `workflow.gates.Gate`.
- Validator MUST NOT depend on a concrete persistence backend.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.workflow.context import PipelineContext
from src.workflow.gates import Gate
from src.workflow.pipeline import Pipeline
from src.workflow.stages import Stage
from src.workflow.types import GateResult


@dataclass(frozen=True, slots=True)
class StageValidation:
    """Validation result for a single stage."""

    stage_name: str
    gate_count: int
    passed_count: int
    failed_count: int
    first_failure: tuple[str, str] | None  # (gate_id, reason) or None
    evaluations: tuple[tuple[str, bool, str | None], ...]  # (gate_id, passed, reason)


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """Aggregate validation report for a full Pipeline run.

    `failed` is True iff any gate failed. `stage_validations` is ordered
    to match the pipeline's stage order.
    """

    cycle_id: str
    stage_validations: tuple[StageValidation, ...]
    total_gates: int
    total_passed: int
    total_failed: int

    @property
    def passed(self) -> bool:
        return self.total_failed == 0

    @property
    def failed(self) -> bool:
        return not self.passed


@dataclass
class Validator:
    """Orchestrates gate evaluation across a Pipeline.

    The Validator takes a Pipeline and a PipelineContext, runs each stage's
    gates via the stage's `run_gates()` method, and accumulates the results
    into a `ValidationReport`. It does not mutate the context beyond the
    events the stages themselves emit (GateEvaluated).
    """

    def validate(
        self,
        pipeline: Pipeline,
        context: PipelineContext,
    ) -> ValidationReport:
        """Evaluate every gate in every stage of the pipeline.

        Args:
            pipeline: The Pipeline whose stages' gates will be evaluated.
            context: The PipelineContext to validate against.

        Returns:
            A `ValidationReport` summarizing per-stage and aggregate results.

        Raises:
            TypeError: If `pipeline` is not a `Pipeline` instance.
        """
        if not isinstance(pipeline, Pipeline):
            raise TypeError(f"Validator expects a Pipeline; got {type(pipeline).__name__}")

        stage_results: list[StageValidation] = []
        total_gates = 0
        total_passed = 0
        total_failed = 0

        for stage in pipeline.stages:
            sv = self._validate_stage(stage, context)
            stage_results.append(sv)
            total_gates += sv.gate_count
            total_passed += sv.passed_count
            total_failed += sv.failed_count

        return ValidationReport(
            cycle_id=str(context.cycle_id),
            stage_validations=tuple(stage_results),
            total_gates=total_gates,
            total_passed=total_passed,
            total_failed=total_failed,
        )

    def _validate_stage(
        self,
        stage: Stage,
        context: PipelineContext,
    ) -> StageValidation:
        gate_results: list[tuple[str, bool, str | None]] = []
        passed = 0
        failed = 0
        first_failure: tuple[str, str] | None = None

        for gate, result in stage.run_gates(context):
            passed_flag = bool(result.passed)
            reason = result.reason if not passed_flag else None
            gate_results.append((gate.id, passed_flag, reason))
            if passed_flag:
                passed += 1
            else:
                failed += 1
                if first_failure is None:
                    first_failure = (gate.id, reason or "unspecified")

        return StageValidation(
            stage_name=stage.name,
            gate_count=len(gate_results),
            passed_count=passed,
            failed_count=failed,
            first_failure=first_failure,
            evaluations=tuple(gate_results),
        )


__all__ = ["StageValidation", "ValidationReport", "Validator"]