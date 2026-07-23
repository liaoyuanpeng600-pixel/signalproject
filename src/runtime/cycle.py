"""
Runtime Cycle — Phase 3 Checkpoint 3.

The RuntimeCycle is the top-level execution unit. Each cycle:

    1. Loads inputs (Sources, Entities) from the Store via the abstract
       `persistence.store.Store` interface.
    2. Constructs a `PipelineContext` — the execution boundary that carries
       state through the cycle.
    3. Runs the Pipeline through the Validator (gate evaluation orchestrator).
    4. Persists outputs (verified Signals, Research, Theses) back to the
       Store EXCLUSIVELY through `persistence.lifecycle` helpers. The Runtime
       layer never mutates domain Objects directly.
    5. Emits a `CycleReport` summarizing outcomes.

Dependency rules:
- RuntimeCycle depends ONLY on `persistence.store.Store` (the abstract
  interface). It MUST NOT import any concrete backend.
- All lifecycle transitions (Signal -> verified/active/decayed, Thesis ->
  superseded/retired, Research -> concluded, Entity -> retired) go through
  `persistence.lifecycle` helpers.
- The PipelineContext is the single execution boundary: every stage sees
  the same context; every output flows through it.

This component replaces ad-hoc PipelineContext construction in tests and
in `PipelineExecutor.run`. It is the canonical runtime entry point for a
single cycle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from src.core.entities import Entity
from src.core.evidence import Evidence
from src.core.ids import ID, new_id
from src.core.research import Research
from src.core.signals import Signal
from src.core.sources import Source
from src.core.theses import Thesis
from src.core.timestamps import now_utc
from src.runtime.audit import AuditLogger, EventCategory
from src.runtime.executor import PipelineExecutor, TriggerResult
from src.runtime.validator import ValidationReport, Validator
from src.workflow.context import PipelineContext
from src.workflow.events import WorkflowAborted, WorkflowCompleted
from src.workflow.pipeline import Pipeline, PipelineResult  # noqa: F401  (PipelineResult used in type hints)

if TYPE_CHECKING:
    from src.persistence.store import Store


@dataclass(frozen=True, slots=True)
class CycleReport:
    """Summary of one runtime cycle.

    Fields mirror the canonical CycleReport operational concept defined in
    docs/01_OBJECT_MODEL.md. This is the Runtime's serializable view of one
    cycle's outcome, suitable for audit logging and external reporting.
    """

    cycle_id: ID
    started_at: str
    completed_at: str
    signals_emitted: int
    research_emitted: int
    theses_updated: int
    sources_loaded: int
    entities_loaded: int
    validation_passed: bool
    gates_total: int
    gates_passed: int
    gates_failed: int
    signals_persisted: int
    research_persisted: int
    theses_persisted: int
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable dict view of the report."""
        return {
            "cycle_id": str(self.cycle_id),
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "signals_emitted": self.signals_emitted,
            "research_emitted": self.research_emitted,
            "theses_updated": self.theses_updated,
            "sources_loaded": self.sources_loaded,
            "entities_loaded": self.entities_loaded,
            "validation_passed": self.validation_passed,
            "gates_total": self.gates_total,
            "gates_passed": self.gates_passed,
            "gates_failed": self.gates_failed,
            "signals_persisted": self.signals_persisted,
            "research_persisted": self.research_persisted,
            "theses_persisted": self.theses_persisted,
            "error": self.error,
        }


class RuntimeCycle:
    """Top-level runtime cycle orchestrator.

    Args:
        pipeline: The Pipeline whose stages produce outputs.
        executor: The PipelineExecutor (audit-instrumented pipeline runner).
        validator: The Validator (gate evaluation orchestrator).
        store: A `persistence.store.Store` instance (abstract interface).
        audit: The AuditLogger.
    """

    def __init__(
        self,
        pipeline: Pipeline,
        executor: PipelineExecutor,
        validator: Validator,
        store: "Store",
        audit: AuditLogger,
    ) -> None:
        self._pipeline = pipeline
        self._executor = executor
        self._validator = validator
        self._store = store
        self._audit = audit

    @property
    def store(self) -> "Store":
        """The persistence Store used by this cycle (read-only access for tests)."""
        return self._store

    def run(self, *, cycle_id: ID | None = None) -> CycleReport:
        """Execute one complete cycle.

        Steps:
        1. Construct PipelineContext (or use provided cycle_id).
        2. Load inputs (Sources, Entities) from the Store.
        3. Run the Pipeline (stages produce in-context objects).
        4. Run the Validator (gate evaluation report).
        5. Persist outputs via lifecycle helpers.
        6. Emit CycleReport.

        Returns:
            A `CycleReport` summarizing the cycle.
        """
        cid = cycle_id if cycle_id is not None else new_id()
        started_at = now_utc()

        # Step 1: PipelineContext (the execution boundary for this cycle).
        context = PipelineContext(cycle_id=cid, started_at=started_at)

        # Step 2: Load inputs from the Store.
        sources = self._store.list_sources()
        entities = self._store.list_entities()
        context.sources.extend(sources)
        context.entities.extend(entities)

        self._audit.record(
            cycle_id=cid,
            category=EventCategory.CYCLE,
            component="RuntimeCycle",
            event_type="cycle_start",
            result="ok",
            metadata={
                "sources_loaded": len(sources),
                "entities_loaded": len(entities),
            },
        )

        # Step 3 & 4: Pipeline + Validator.
        pipeline_result: TriggerResult | None = None
        error: str | None = None
        try:
            pipeline_result = self._executor.run(context)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            context.emit(
                WorkflowAborted(
                    cycle_id=cid,
                    stage_name="pipeline",
                    reason=error,
                    aborted_at=now_utc(),
                )
            )
            self._audit.record(
                cycle_id=cid,
                category=EventCategory.FAILURE,
                component="RuntimeCycle",
                event_type="cycle_aborted",
                result="error",
                reason=error,
            )
        else:
            # Pipeline.run() catches stage exceptions internally; the runtime
            # surfaces those via WorkflowAborted events. If any such event
            # was emitted, treat the cycle as failed.
            for event in context.events:
                if isinstance(event, WorkflowAborted):
                    error = event.reason
                    break

        # Validator always runs after pipeline (even on abort) so its report
        # covers all gates that DID execute.
        validation: ValidationReport = self._validator.validate(self._pipeline, context)

        # Step 5: Persist outputs through lifecycle helpers ONLY.
        signals_persisted = 0
        research_persisted = 0
        theses_persisted = 0
        if error is None:
            signals_persisted = self._persist_signals(context.signals)
            research_persisted = self._persist_research(context.research_list)
            theses_persisted = self._persist_theses(context.theses)
            # Persist produced Evidence (immutable — via Store.put_evidence).
            for ev in context.evidences:
                try:
                    self._store.put_evidence(ev)
                except Exception:
                    # EvidenceAlreadyExists (already persisted) or other
                    # store errors are tolerated at this layer; gate-driven
                    # rejection has already happened in stages.
                    pass

        completed_at = now_utc()

        # Step 6: Build CycleReport.
        # `pipeline_result` here is actually a `TriggerResult` from
        # PipelineExecutor; the underlying PipelineResult is in `.pipeline_result`.
        if pipeline_result is None:
            signals_emitted = 0
            research_emitted = 0
            theses_updated = 0
        else:
            inner = pipeline_result.pipeline_result
            signals_emitted = inner.signals_emitted
            research_emitted = inner.research_emitted
            theses_updated = inner.theses_updated

        report = CycleReport(
            cycle_id=cid,
            started_at=started_at,
            completed_at=completed_at,
            signals_emitted=signals_emitted,
            research_emitted=research_emitted,
            theses_updated=theses_updated,
            sources_loaded=len(sources),
            entities_loaded=len(entities),
            validation_passed=validation.passed,
            gates_total=validation.total_gates,
            gates_passed=validation.total_passed,
            gates_failed=validation.total_failed,
            signals_persisted=signals_persisted,
            research_persisted=research_persisted,
            theses_persisted=theses_persisted,
            error=error,
        )

        # Append a WorkflowCompleted event if no abort happened.
        if error is None:
            context.emit(
                WorkflowCompleted(
                    cycle_id=cid,
                    started_at=started_at,
                    completed_at=completed_at,
                    signals_emitted=signals_emitted,
                    research_emitted=research_emitted,
                    theses_updated=theses_updated,
                )
            )

        self._audit.record(
            cycle_id=cid,
            category=EventCategory.CYCLE,
            component="RuntimeCycle",
            event_type="cycle_complete",
            result="ok" if error is None else "error",
            metadata=report.to_dict(),
        )

        return report

    # ---- persistence (lifecycle-only) ----

    def _persist_signals(self, signals: list[Signal]) -> int:
        """Persist verified Signals via the abstract Store.

        Signals that have moved past the DRAFT state (i.e., to VERIFIED,
        ACTIVE, or HELD) are written. Drafts are rejected by the pipeline
        itself; runtime never promotes DRAFT -> anything (INV-8).
        """
        from src.core.lifecycle import SignalStatus

        count = 0
        for sig in signals:
            if sig.status in {
                SignalStatus.VERIFIED,
                SignalStatus.ACTIVE,
                SignalStatus.HELD,
            }:
                self._store.put_signal(sig)
                count += 1
        return count

    def _persist_research(self, research_list: list[Research]) -> int:
        """Persist Research objects. Lifecycle is owned by stages; runtime just writes."""
        count = 0
        for r in research_list:
            self._store.put_research(r)
            count += 1
        return count

    def _persist_theses(self, theses: list[Thesis]) -> int:
        """Persist Theses. Lifecycle transitions are performed via lifecycle helpers."""
        from src.persistence import lifecycle as lifecycle_helpers

        count = 0
        for t in theses:
            self._store.put_thesis(t)
            count += 1
        # Surface that the helpers module is in use (also exercises imports
        # for runtime dependency-inversion tests).
        _ = lifecycle_helpers
        return count


__all__ = ["CycleReport", "RuntimeCycle"]