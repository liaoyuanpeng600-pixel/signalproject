"""Tests for RuntimeCycle (Runtime Checkpoint 3)."""

from __future__ import annotations

from typing import Any

import pytest

from src.core.entities import Entity, EntityKind
from src.core.evidence import Evidence, Quality
from src.core.ids import ID, new_id
from src.core.invariants import Score
from src.core.lifecycle import ResearchStatus
from src.core.research import Research
from src.core.signals import (
    EntityRef,
    Signal,
    SignalDirection,
    SignalHorizon,
    SignalStatus,
)
from src.core.sources import Source, SourceType
from src.core.theses import Thesis, ThesisStatus
from src.persistence.in_memory import InMemoryStore  # test boundary only
from src.persistence.store import Store
from src.runtime.audit import AuditLogger
from src.runtime.cycle import CycleReport, RuntimeCycle
from src.runtime.executor import PipelineExecutor
from src.runtime.validator import Validator
from src.workflow.context import PipelineContext
from src.workflow.pipeline import Pipeline
from src.workflow.stages import Stage


# ----------------------- helpers -----------------------


def _store() -> Store:
    return InMemoryStore()


def _entity(name: str = "ACME") -> Entity:
    return Entity.create(kind=EntityKind.COMPANY, name=name)


def _source() -> Source:
    return Source.create(
        type=SourceType.NEWS_ARTICLE,
        url="https://example.com/news/1",
        name="Example News",
    )


def _evidence() -> Evidence:
    return Evidence.create(
        source_ids=(ID("src-1"),),
        content="ACME announced a 10% dividend increase.",
        quality=Quality(0.9, 0.8, 0.95),
    )


def _score() -> Score:
    return Score(magnitude=0.5, confidence=0.5, timeliness=0.5, novelty=0.5, actionability=0.5)


def _signal(entity: Entity, ev: Evidence) -> Signal:
    return Signal.create(
        entity_ref=EntityRef(id=entity.id, kind=entity.kind.value),
        type="capital_action",
        claim="ACME dividend up 10%",
        evidence_ids=(ev.id,),
        direction=SignalDirection.BULLISH,
        horizon=SignalHorizon.SHORT,
        score=_score(),
    )


def _cycle(
    store: Store | None = None,
    *,
    pipeline: Pipeline | None = None,
) -> RuntimeCycle:
    s = store if store is not None else _store()
    p = pipeline if pipeline is not None else Pipeline()
    return RuntimeCycle(
        pipeline=p,
        executor=PipelineExecutor(pipeline=p, audit=AuditLogger()),
        validator=Validator(),
        store=s,
        audit=AuditLogger(),
    )


# ----------------------- PipelineContext propagation -----------------------


class TestPipelineContextPropagation:
    def test_run_loads_inputs_into_context(self) -> None:
        store = _store()
        entity = _entity()
        source = _source()
        store.put_entity(entity)
        store.put_source(source)
        cycle = _cycle(store=store)
        # Use a custom pipeline that records what it sees in context.
        seen: dict[str, Any] = {}

        class _ProbeStage(Stage):
            @property
            def name(self) -> str:
                return "probe"

            @property
            def gates(self) -> list[Any]:
                return []

            def execute(self, context: PipelineContext) -> Any:
                seen["sources"] = list(context.sources)
                seen["entities"] = list(context.entities)
                seen["cycle_id"] = context.cycle_id
                return None

        cycle._pipeline = Pipeline(stages=[_ProbeStage()])  # type: ignore[attr-defined]
        cycle._executor = PipelineExecutor(pipeline=cycle._pipeline, audit=AuditLogger())  # type: ignore[attr-defined]
        report = cycle.run()
        assert seen["sources"] == [source]
        assert seen["entities"] == [entity]
        assert seen["cycle_id"] == report.cycle_id

    def test_cycle_id_is_consistent_throughout(self) -> None:
        store = _store()
        cycle = _cycle(store=store)
        report = cycle.run()
        assert str(report.cycle_id) != ""

    def test_explicit_cycle_id_preserved(self) -> None:
        store = _store()
        cycle = _cycle(store=store)
        cid = new_id()
        report = cycle.run(cycle_id=cid)
        assert report.cycle_id == cid


# ----------------------- persistence wiring -----------------------


class TestPersistenceWiring:
    def test_outputs_persisted_via_store_interface(self) -> None:
        store = _store()
        entity = _entity()
        evidence = _evidence()
        store.put_entity(entity)
        store.put_evidence(evidence)
        cycle = _cycle(store=store)

        # Inject a known Signal directly into context after stages run.
        sig = _signal(entity, evidence).verify().activate()

        # Use a custom pipeline that produces one verified signal.
        class _ProduceSignalStage(Stage):
            @property
            def name(self) -> str:
                return "produce_signal"

            @property
            def gates(self) -> list[Any]:
                return []

            def execute(self, context: PipelineContext) -> Any:
                context.signals.append(sig)
                return None

        cycle._pipeline = Pipeline(stages=[_ProduceSignalStage()])  # type: ignore[attr-defined]
        cycle._executor = PipelineExecutor(pipeline=cycle._pipeline, audit=AuditLogger())  # type: ignore[attr-defined]

        report = cycle.run()
        # Signal was persisted via Store (verified+active are written).
        assert store.get_signal(str(sig.id)) is not None
        assert store.get_signal(str(sig.id)).status == SignalStatus.ACTIVE
        assert report.signals_persisted == 1

    def test_draft_signals_are_not_persisted(self) -> None:
        store = _store()
        entity = _entity()
        evidence = _evidence()
        store.put_entity(entity)
        store.put_evidence(evidence)
        cycle = _cycle(store=store)

        # DRAFT signal — should NOT be persisted (INV-8: drafts never reach users).
        sig = _signal(entity, evidence)  # status=DRAFT

        class _ProduceDraftStage(Stage):
            @property
            def name(self) -> str:
                return "produce_draft"

            @property
            def gates(self) -> list[Any]:
                return []

            def execute(self, context: PipelineContext) -> Any:
                context.signals.append(sig)
                return None

        cycle._pipeline = Pipeline(stages=[_ProduceDraftStage()])  # type: ignore[attr-defined]
        cycle._executor = PipelineExecutor(pipeline=cycle._pipeline, audit=AuditLogger())  # type: ignore[attr-defined]
        report = cycle.run()
        assert store.get_signal(str(sig.id)) is None
        assert report.signals_persisted == 0

    def test_research_persisted(self) -> None:
        store = _store()
        entity = _entity()
        store.put_entity(entity)
        cycle = _cycle(store=store)

        research = Research.create(
            entity_ref=EntityRef(id=entity.id, kind=entity.kind.value),
            question="Is ACME overvalued?",
            signal_ids=(ID("s-1"),),
        )

        class _ProduceResearchStage(Stage):
            @property
            def name(self) -> str:
                return "produce_research"

            @property
            def gates(self) -> list[Any]:
                return []

            def execute(self, context: PipelineContext) -> Any:
                context.research_list.append(research)
                return None

        cycle._pipeline = Pipeline(stages=[_ProduceResearchStage()])  # type: ignore[attr-defined]
        cycle._executor = PipelineExecutor(pipeline=cycle._pipeline, audit=AuditLogger())  # type: ignore[attr-defined]
        report = cycle.run()
        assert store.get_research(str(research.id)) is not None
        assert report.research_persisted == 1

    def test_thesis_persisted(self) -> None:
        store = _store()
        entity = _entity()
        store.put_entity(entity)
        cycle = _cycle(store=store)

        thesis = Thesis.create(
            entity_ref=EntityRef(id=entity.id, kind=entity.kind.value),
            interpretation="ACME is a growth story",
        )

        class _ProduceThesisStage(Stage):
            @property
            def name(self) -> str:
                return "produce_thesis"

            @property
            def gates(self) -> list[Any]:
                return []

            def execute(self, context: PipelineContext) -> Any:
                context.theses.append(thesis)
                return None

        cycle._pipeline = Pipeline(stages=[_ProduceThesisStage()])  # type: ignore[attr-defined]
        cycle._executor = PipelineExecutor(pipeline=cycle._pipeline, audit=AuditLogger())  # type: ignore[attr-defined]
        report = cycle.run()
        assert store.get_thesis(str(thesis.id)) is not None
        assert report.theses_persisted == 1

    def test_evidence_persisted(self) -> None:
        store = _store()
        evidence = _evidence()
        cycle = _cycle(store=store)

        class _ProduceEvidenceStage(Stage):
            @property
            def name(self) -> str:
                return "produce_evidence"

            @property
            def gates(self) -> list[Any]:
                return []

            def execute(self, context: PipelineContext) -> Any:
                context.evidences.append(evidence)
                return None

        cycle._pipeline = Pipeline(stages=[_ProduceEvidenceStage()])  # type: ignore[attr-defined]
        cycle._executor = PipelineExecutor(pipeline=cycle._pipeline, audit=AuditLogger())  # type: ignore[attr-defined]
        cycle.run()
        # Evidence is persisted via Store.put_evidence (write-once semantics).
        assert store.get_evidence(str(evidence.id)) is not None


# ----------------------- lifecycle helpers used -----------------------


class TestLifecycleHelpers:
    def test_cycle_uses_lifecycle_module(self) -> None:
        """RuntimeCycle must persist lifecycle transitions via lifecycle helpers,
        not direct mutation. We verify by importing the lifecycle module from
        the same package and asserting it is referenced in cycle.py.
        """
        import src.runtime.cycle as cycle_mod

        source = cycle_mod.__file__ or ""
        with open(source, encoding="utf-8") as f:
            contents = f.read()
        assert "persistence.lifecycle" in contents
        # Also: it must NOT import a concrete Store backend.
        assert "persistence.in_memory" not in contents
        assert "InMemoryStore" not in contents


# ----------------------- cycle report -----------------------


class TestCycleReport:
    def test_report_has_all_required_fields(self) -> None:
        store = _store()
        cycle = _cycle(store=store)
        report = cycle.run()
        assert isinstance(report, CycleReport)
        assert report.started_at <= report.completed_at
        assert report.sources_loaded == 0
        assert report.entities_loaded == 0

    def test_report_counts_inputs(self) -> None:
        store = _store()
        store.put_entity(_entity("A"))
        store.put_entity(_entity("B"))
        store.put_source(_source())
        cycle = _cycle(store=store)
        report = cycle.run()
        assert report.entities_loaded == 2
        assert report.sources_loaded == 1

    def test_report_validation_passed_true_on_empty_pipeline(self) -> None:
        store = _store()
        cycle = _cycle(store=store, pipeline=Pipeline(stages=[]))
        report = cycle.run()
        assert report.validation_passed is True
        assert report.gates_total == 0
        assert report.gates_failed == 0

    def test_report_to_dict_is_json_serializable(self) -> None:
        import json

        store = _store()
        cycle = _cycle(store=store)
        report = cycle.run()
        json.dumps(report.to_dict())


# ----------------------- error handling -----------------------


class TestCycleErrorHandling:
    def test_pipeline_failure_yields_error_report(self) -> None:
        """A stage that emits a WorkflowAborted event must surface as a cycle error.

        Per Workflow Model, stages signal infrastructure-level aborts by
        emitting a WorkflowAborted event on the context. The RuntimeCycle
        observes this and records the error on the CycleReport. (Plain
        exceptions raised in stages are caught by Pipeline.run per Phase 2
        architecture; the runtime surface is the event.)
        """
        from src.core.timestamps import now_utc
        from src.workflow.events import WorkflowAborted

        store = _store()
        abort_reason = "stage kaboom"

        class _AbortingStage(Stage):
            @property
            def name(self) -> str:
                return "abort"

            @property
            def gates(self) -> list[Any]:
                return []

            def execute(self, context: PipelineContext) -> Any:
                context.emit(
                    WorkflowAborted(
                        cycle_id=context.cycle_id,
                        stage_name="abort",
                        reason=abort_reason,
                        aborted_at=now_utc(),
                    )
                )
                return None

        cycle = _cycle(store=store, pipeline=Pipeline(stages=[_AbortingStage()]))
        report = cycle.run()
        assert report.error is not None
        assert abort_reason in report.error
        # No outputs persisted on abort.
        assert report.signals_persisted == 0

    def test_unhandled_exception_in_executor_records_error(self) -> None:
        """If the executor itself raises (bypassing Pipeline.run's catch),
        RuntimeCycle catches it and emits a CycleReport with error set."""
        from typing import Any

        class _RaisingExecutor:
            def run(self, context: PipelineContext) -> Any:
                raise RuntimeError("executor kaboom")

        cycle = RuntimeCycle(
            pipeline=Pipeline(),
            executor=_RaisingExecutor(),  # type: ignore[arg-type]
            validator=Validator(),
            store=_store(),
            audit=AuditLogger(),
        )
        report = cycle.run()
        assert report.error is not None
        assert "kaboom" in report.error
        assert report.signals_persisted == 0


# ----------------------- dependency inversion -----------------------


class TestDependencyInversion:
    def test_runtime_cycle_imports_only_abstract_store(self) -> None:
        import src.runtime.cycle as c

        source = c.__file__ or ""
        with open(source, encoding="utf-8") as f:
            contents = f.read()
        # Must import the abstract Store interface (TYPE_CHECKING is fine).
        assert "persistence.store" in contents
        # Must NOT import any concrete backend.
        assert "from src.persistence.in_memory" not in contents
        assert "import src.persistence.in_memory" not in contents

    def test_runtime_uses_only_abstract_store_type_hint(self) -> None:
        """Inspect the runtime package: it should not import concrete backends.

        We walk from this test file up to the project root and scan
        `src/runtime/`. Tests under `tests/unit/runtime/` are explicitly
        excluded — they may import concrete backends at the test boundary
        (e.g., `InMemoryStore` to construct fixtures); the rule applies only
        to production runtime code.
        """
        import os

        tests_dir = os.path.dirname(os.path.abspath(__file__))
        # tests/unit/runtime/test_cycle.py -> tests/unit/runtime
        # Walk up until we find a sibling 'src' directory.
        cur = tests_dir
        src_dir = None
        for _ in range(6):
            candidate = os.path.join(cur, "src")
            if os.path.isdir(candidate):
                src_dir = candidate
                break
            cur = os.path.dirname(cur)
        assert src_dir is not None, "could not locate project src/"

        runtime_dir = os.path.join(src_dir, "runtime")
        assert os.path.isdir(runtime_dir), f"runtime dir missing: {runtime_dir}"

        # Match actual import statements only (not docstring mentions).
        import re

        import_re = re.compile(
            r"^\s*(?:from\s+src\.persistence\.in_memory|import\s+src\.persistence\.in_memory)",
            re.MULTILINE,
        )

        for fname in sorted(os.listdir(runtime_dir)):
            if not fname.endswith(".py"):
                continue
            path = os.path.join(runtime_dir, fname)
            with open(path, encoding="utf-8") as f:
                contents = f.read()
            matches = import_re.findall(contents)
            assert not matches, (
                f"{fname} imports concrete persistence backend: {matches}"
            )


# ----------------------- end-to-end integration -----------------------


class TestEndToEnd:
    def test_full_cycle_loads_runs_persists(self) -> None:
        """End-to-end: load from Store, run pipeline+validator, persist outputs."""
        store = _store()
        entity = _entity("ACME")
        evidence = _evidence()
        store.put_entity(entity)
        store.put_evidence(evidence)

        sig = _signal(entity, evidence).verify().activate()

        class _Stage(Stage):
            @property
            def name(self) -> str:
                return "end_to_end"

            @property
            def gates(self) -> list[Any]:
                return []

            def execute(self, context: PipelineContext) -> Any:
                # Mimic real pipeline behavior: signals produced by stages.
                context.signals.append(sig)
                return None

        pipeline = Pipeline(stages=[_Stage()])
        executor = PipelineExecutor(pipeline=pipeline, audit=AuditLogger())
        cycle = RuntimeCycle(
            pipeline=pipeline,
            executor=executor,
            validator=Validator(),
            store=store,
            audit=AuditLogger(),
        )
        report = cycle.run()
        # Outputs persisted.
        assert store.get_signal(str(sig.id)) is not None
        # Report reflects run.
        assert report.signals_persisted == 1
        assert report.entities_loaded == 1
        assert report.validation_passed is True
        assert report.error is None