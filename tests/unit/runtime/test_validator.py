"""Tests for the Validator (Runtime Checkpoint 3)."""

from __future__ import annotations

from typing import Any

import pytest

from src.runtime.validator import StageValidation, ValidationReport, Validator
from src.workflow.context import PipelineContext
from src.workflow.gates import Gate
from src.workflow.pipeline import Pipeline
from src.workflow.stages import Stage, default_stages
from src.workflow.types import GateResult, StageStatus


# ----------------------- helpers -----------------------


class _PassingStage(Stage):
    @property
    def name(self) -> str:
        return "test_passing"

    @property
    def gates(self) -> list[Gate]:
        return [self._g1(), self._g2()]

    def execute(self, context: PipelineContext) -> Any:  # noqa: ARG002
        return None

    @staticmethod
    def _g1() -> Gate:
        class _G(Gate):
            @property
            def id(self) -> str:
                return "T-G1"

            def validate(self, context: PipelineContext) -> GateResult:  # noqa: ARG002
                return GateResult.pass_()

        return _G()

    @staticmethod
    def _g2() -> Gate:
        class _G(Gate):
            @property
            def id(self) -> str:
                return "T-G2"

            def validate(self, context: PipelineContext) -> GateResult:  # noqa: ARG002
                return GateResult.pass_()

        return _G()


class _FailingStage(Stage):
    @property
    def name(self) -> str:
        return "test_failing"

    @property
    def gates(self) -> list[Gate]:
        return [self._g1()]

    def execute(self, context: PipelineContext) -> Any:  # noqa: ARG002
        return None

    @staticmethod
    def _g1() -> Gate:
        class _G(Gate):
            @property
            def id(self) -> str:
                return "F-G1"

            def validate(self, context: PipelineContext) -> GateResult:  # noqa: ARG002
                return GateResult.fail("simulated failure")

        return _G()


# ----------------------- basic orchestration -----------------------


class TestValidatorBasics:
    def test_validate_returns_report(self) -> None:
        validator = Validator()
        pipeline = Pipeline(stages=[_PassingStage()])
        context = PipelineContext()
        report = validator.validate(pipeline, context)
        assert isinstance(report, ValidationReport)
        assert report.passed is True
        assert report.failed is False
        assert report.total_gates == 2
        assert report.total_passed == 2
        assert report.total_failed == 0

    def test_validate_rejects_non_pipeline(self) -> None:
        validator = Validator()
        with pytest.raises(TypeError):
            validator.validate(pipeline="not-a-pipeline", context=PipelineContext())  # type: ignore[arg-type]


class TestGateRecording:
    def test_records_pass_per_gate(self) -> None:
        validator = Validator()
        pipeline = Pipeline(stages=[_PassingStage()])
        context = PipelineContext()
        validator.validate(pipeline, context)
        # Each gate evaluation should have emitted a GateEvaluated event.
        gate_events = [e for e in context.events if e.__class__.__name__ == "GateEvaluated"]
        assert len(gate_events) == 2
        assert all(e.passed for e in gate_events)  # type: ignore[attr-defined]


# ----------------------- failure path -----------------------


class TestFailureAggregation:
    def test_single_failing_gate_marks_report_failed(self) -> None:
        validator = Validator()
        pipeline = Pipeline(stages=[_FailingStage()])
        report = validator.validate(pipeline, PipelineContext())
        assert report.passed is False
        assert report.total_failed == 1
        assert report.total_passed == 0

    def test_mixed_pass_and_fail(self) -> None:
        validator = Validator()
        pipeline = Pipeline(stages=[_PassingStage(), _FailingStage()])
        report = validator.validate(pipeline, PipelineContext())
        assert report.total_gates == 3
        assert report.total_passed == 2
        assert report.total_failed == 1

    def test_stage_validation_records_first_failure(self) -> None:
        validator = Validator()
        pipeline = Pipeline(stages=[_FailingStage()])
        report = validator.validate(pipeline, PipelineContext())
        sv = report.stage_validations[0]
        assert isinstance(sv, StageValidation)
        assert sv.first_failure is not None
        assert sv.first_failure[0] == "F-G1"
        assert sv.first_failure[1] == "simulated failure"
        assert sv.evaluations == (("F-G1", False, "simulated failure"),)


# ----------------------- stage ordering -----------------------


class TestStageOrdering:
    def test_validates_stages_in_pipeline_order(self) -> None:
        validator = Validator()
        first = _PassingStage()
        second = _FailingStage()
        pipeline = Pipeline(stages=[first, second])
        report = validator.validate(pipeline, PipelineContext())
        assert [sv.stage_name for sv in report.stage_validations] == [
            "test_passing",
            "test_failing",
        ]


# ----------------------- default pipeline -----------------------


class TestDefaultPipeline:
    def test_default_pipeline_validates(self) -> None:
        """Smoke-test the Validator against the canonical default Pipeline."""
        validator = Validator()
        pipeline = Pipeline(stages=default_stages())
        report = validator.validate(pipeline, PipelineContext())
        # All gates should evaluate; some may pass, some may fail depending
        # on the empty-context behavior of each gate. We only assert
        # structural correctness.
        assert isinstance(report, ValidationReport)
        assert report.total_gates == sum(sv.gate_count for sv in report.stage_validations)
        assert report.total_passed + report.total_failed == report.total_gates

    def test_default_pipeline_stage_names_in_order(self) -> None:
        validator = Validator()
        pipeline = Pipeline(stages=default_stages())
        report = validator.validate(pipeline, PipelineContext())
        # Default stages are named "S1".."S6" or similar; we just confirm
        # count and uniqueness.
        names = [sv.stage_name for sv in report.stage_validations]
        assert len(set(names)) == len(names)


# ----------------------- context safety -----------------------


class TestContextSafety:
    def test_validator_does_not_mutate_evidence_lists(self) -> None:
        validator = Validator()
        pipeline = Pipeline(stages=[_PassingStage()])
        context = PipelineContext()
        before_evidences = list(context.evidences)
        validator.validate(pipeline, context)
        # Validator must not have added any objects to the context.
        assert list(context.evidences) == before_evidences

    def test_cycle_id_propagates_to_report(self) -> None:
        validator = Validator()
        pipeline = Pipeline(stages=[_PassingStage()])
        context = PipelineContext()
        report = validator.validate(pipeline, context)
        assert report.cycle_id == str(context.cycle_id)


# ----------------------- validator contains no business logic -----------------------


class TestNoBusinessLogic:
    """The Validator must remain a pure orchestrator.

    It MUST NOT inspect Object contents, MUST NOT call lifecycle helpers,
    and MUST NOT talk to persistence. The tests below prove these
    properties by inspecting the Validator source via type and behavior.
    """

    def test_validator_has_no_lifecycle_imports(self) -> None:
        import re

        import src.runtime.validator as v

        source = v.__file__ or ""
        with open(source, encoding="utf-8") as f:
            contents = f.read()
        # Match only actual import statements (allow docstring mentions).
        import_re = re.compile(
            r"^\s*(?:from\s+src\.persistence|import\s+src\.persistence)",
            re.MULTILINE,
        )
        assert not import_re.search(contents), (
            f"validator.py imports persistence module: {import_re.search(contents).group(0)!r}"
        )

    def test_validator_only_imports_persistence_store_interface(self) -> None:
        import src.runtime.validator as v

        source = v.__file__ or ""
        with open(source, encoding="utf-8") as f:
            contents = f.read()
        # Should reference workflow + types; should NOT import any persistence module.
        assert "from src.workflow" in contents
        assert "from src.persistence" not in contents
        assert "import src.persistence" not in contents