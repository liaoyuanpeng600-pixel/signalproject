"""
Workflow Stages — all 6 stages per Workflow Model §"Stages".

Each Stage:
- Has a name (e.g., "S1", "source_observation")
- Has a set of gates
- Executes its logic via interfaces (SourceObserver, EvidenceProducer, etc.)
- Returns a StageResult

Stages are PURE ORCHESTRATORS. They:
1. Call domain interfaces to produce candidate Objects
2. Run gates against the pipeline context
3. Route failures to appropriate paths
4. Update Object state via domain methods (which go through lifecycle)

Stages do NOT:
- Implement business logic (LLM calls, parsing, etc.)
- Persist Objects (delegated to Persistence interface)
- Make decisions about workflow structure (Pipeline does this)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable
from typing import Protocol

from src.core.entities import Entity
from src.core.evidence import Evidence, Quality, SourceType
from src.core.ids import ID, new_id
from src.core.invariants import Score
from src.core.lifecycle import assert_transition
from src.core.research import Research, ResearchStatus
from src.core.signals import (
    EntityRef,
    Signal,
    SignalDirection,
    SignalHorizon,
    SignalStatus,
)
from src.core.sources import Source, SourceStatus
from src.core.theses import Thesis, ThesisStatus
from src.core.timestamps import now_utc
from src.workflow.context import PipelineContext
from src.workflow.events import ObjectRouted, StageCompleted, StageStarted
from src.workflow.gates import (
    Gate,
    STAGE_1_GATES,
    STAGE_2_GATES,
    STAGE_3_GATES,
    STAGE_4_GATES,
    STAGE_5_GATES,
    STAGE_6_GATES,
)
from src.workflow.types import (
    CandidateObservation,
    FailurePath,
    StageResult,
    StageStatus,
)


# ===========================================================================
# Stage Interfaces (Protocols)
# ===========================================================================
#
# These define what each stage needs from "implementation". For Phase 2,
# concrete implementations are out of scope (they come in Phase 3+ Runtime).
# The workflow defines the interface; tests provide stub implementations.


class SourceObserver(Protocol):
    """Interface for Stage 1 to observe Sources.

    Implementations fetch from external sources (HTTP, RSS, etc.) and
    produce CandidateObservation objects.
    """

    def observe(self, source: Source) -> list[CandidateObservation]:
        ...


class EvidenceProducer(Protocol):
    """Interface for Stage 2 to produce Evidence from Candidates.

    Implementations package raw information into immutable Evidence with
    provenance and quality.
    """

    def produce(self, candidate: CandidateObservation, source: Source) -> Evidence:
        ...


class SignalExtractor(Protocol):
    """Interface for Stage 3 to extract Signals from Evidence.

    Implementations produce candidate Signals in DRAFT status; gates then
    validate them.
    """

    def extract(self, evidence: Evidence, entity: Entity) -> list[Signal]:
        ...


class ResearchSynthesizer(Protocol):
    """Interface for Stage 4 to synthesize Research from Signals."""

    def synthesize(
        self, signals: list[Signal], entity: Entity, question: str
    ) -> Research:
        ...


class ThesisCrystallizer(Protocol):
    """Interface for Stage 5 to crystallize a Thesis from Research."""

    def crystallize(self, research: Research, prior_thesis: Thesis | None) -> Thesis:
        ...


class KnowledgeIntegrator(Protocol):
    """Interface for Stage 6 to integrate a Thesis into Knowledge."""

    def integrate(self, thesis: Thesis) -> None:
        ...


# ===========================================================================
# Stage Base
# ===========================================================================


class Stage(ABC):
    """Base class for all workflow stages."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Stage identifier (e.g., 'S1', 'source_observation')."""

    @property
    @abstractmethod
    def gates(self) -> list[Gate]:
        """Gates evaluated by this stage."""

    @abstractmethod
    def execute(self, context: PipelineContext) -> StageResult:
        """Execute the stage's logic and return a result."""

    def run_gates(self, context: PipelineContext) -> list[tuple[Gate, object]]:
        """Run all gates and collect (gate, result) pairs.

        Records each gate evaluation as an event.
        Returns a list of (gate, result) pairs.
        """
        results: list[tuple[Gate, object]] = []
        for gate in self.gates:
            result = gate.validate(context)
            gate.record_evaluation(context, self.name, result)
            results.append((gate, result))
            if not result.passed:
                # Once a gate fails, subsequent gates in this stage may
                # not be meaningful. We continue to record evaluations for
                # audit, but the stage will fail.
                continue
        return results

    def all_gates_passed(self, results: list[tuple[Gate, object]]) -> bool:
        """Check whether all gates passed."""
        return all(result.passed for _, result in results)

    def first_failure(
        self, results: list[tuple[Gate, object]]
    ) -> tuple[Gate, object] | None:
        """Return the first failing gate and its result, or None."""
        for gate, result in results:
            if not result.passed:
                return (gate, result)
        return None

    def route_to_failure_path(
        self,
        context: PipelineContext,
        gate: Gate,
        result: object,
        object_id: ID,
        object_kind: str,
    ) -> None:
        """Route an Object to its failure-path destination.

        Emits an ObjectRouted event.
        """
        destination = gate.failure_path.value
        context.emit(
            ObjectRouted(
                cycle_id=context.cycle_id,
                stage_name=self.name,
                object_id=object_id,
                object_kind=object_kind,
                destination=destination,
                reason=result.reason or "unknown",
                routed_at=now_utc(),
            )
        )


# ===========================================================================
# Stage 1 — Source Observation
# ===========================================================================


class SourceObservationStage(Stage):
    """Stage 1: Observe Sources and produce Candidate observations.

    For each active Source, calls SourceObserver to extract candidates.
    Applies S1-G1, S1-G2, S1-G3 gates. Failures route to Degraded or Flag.
    """

    def __init__(self, observer: SourceObserver | None = None):
        self._observer = observer
        self._gates = STAGE_1_GATES

    @property
    def name(self) -> str:
        return "S1"

    @property
    def gates(self) -> list[Gate]:
        return self._gates

    def execute(self, context: PipelineContext) -> StageResult:
        context.emit(
            StageStarted(cycle_id=context.cycle_id, stage_name=self.name, started_at=now_utc())
        )

        # Observe each source. The observer is injected; if None, skip.
        if self._observer is not None:
            for source in context.sources:
                if source.status != SourceStatus.ACTIVE:
                    continue  # Skip non-active sources
                try:
                    candidates = self._observer.observe(source)
                except Exception as e:
                    # S1-G1: Source unreachable or content failure
                    source_transition = source.transition(SourceStatus.DEACTIVATED)
                    if source_transition not in context.degraded_sources:
                        context.degraded_sources.append(source_transition)
                    continue

                for candidate in candidates:
                    # Per-candidate gate checks
                    if not candidate.content.strip():
                        # S1-G2 fail
                        context.flagged_candidates.append(candidate)
                        continue

                    try:
                        from datetime import datetime, timezone

                        ts = datetime.fromisoformat(candidate.source_timestamp)
                        if ts.tzinfo is None or ts > datetime.now(timezone.utc):
                            # S1-G3 fail
                            context.flagged_candidates.append(candidate)
                            continue
                        age_days = (
                            datetime.now(timezone.utc) - ts.astimezone(timezone.utc)
                        ).days
                        if age_days > 30:
                            context.flagged_candidates.append(candidate)
                            continue
                    except ValueError:
                        context.flagged_candidates.append(candidate)
                        continue

                    context.candidates.append(candidate)

        # Run gates for cycle-level validation
        results = self.run_gates(context)
        first_fail = self.first_failure(results)

        if first_fail is not None:
            gate, result = first_fail
            # Stage 1 failures don't abort the cycle
            context.emit(
                StageCompleted(
                    cycle_id=context.cycle_id,
                    stage_name=self.name,
                    status=StageStatus.FAIL_DEGRADED
                    if gate.failure_path == FailurePath.DEGRADED
                    else StageStatus.FAIL_FLAG,
                    completed_at=now_utc(),
                )
            )
            return StageResult(
                status=StageStatus.FAIL_DEGRADED
                if gate.failure_path == FailurePath.DEGRADED
                else StageStatus.FAIL_FLAG,
                failure_path=gate.failure_path,
                failure_reason=result.reason,
                retryable=gate.retryable,
            )

        context.emit(
            StageCompleted(
                cycle_id=context.cycle_id,
                stage_name=self.name,
                status=StageStatus.ADVANCE,
                completed_at=now_utc(),
            )
        )
        return StageResult(status=StageStatus.ADVANCE)


# ===========================================================================
# Stage 2 — Evidence Production
# ===========================================================================


class EvidenceProductionStage(Stage):
    """Stage 2: Produce Evidence from Candidate observations.

    For each Candidate, calls EvidenceProducer to produce Evidence.
    Applies S2-G1, S2-G2, S2-G3, S2-G4 gates. Failures route to Reject.
    """

    def __init__(self, producer: EvidenceProducer | None = None):
        self._producer = producer
        self._gates = STAGE_2_GATES

    @property
    def name(self) -> str:
        return "S2"

    @property
    def gates(self) -> list[Gate]:
        return self._gates

    def execute(self, context: PipelineContext) -> StageResult:
        context.emit(
            StageStarted(cycle_id=context.cycle_id, stage_name=self.name, started_at=now_utc())
        )

        if self._producer is not None:
            for candidate in list(context.candidates):
                source = next(
                    (s for s in context.sources if s.id == candidate.source_id),
                    None,
                )
                if source is None:
                    context.candidates.remove(candidate)
                    continue

                try:
                    evidence = self._producer.produce(candidate, source)
                except Exception:
                    # Producer failed; route to reject and consume candidate
                    context.candidates.remove(candidate)
                    continue

                # Candidate is consumed regardless of gate outcome.
                context.candidates.remove(candidate)

                if evidence.source_ids and evidence.content.strip():
                    context.evidences.append(evidence)
                else:
                    # Failed S2-G1 or S2-G2
                    context.rejected_evidences.append(evidence)
                    self.route_to_failure_path(
                        context,
                        gate=self._gates[0],  # S2-G1
                        result=type("FakeResult", (), {"reason": "evidence production failed"})(),
                        object_id=evidence.id,
                        object_kind="candidate",
                    )

        results = self.run_gates(context)
        first_fail = self.first_failure(results)

        if first_fail is not None:
            gate, result = first_fail
            context.emit(
                StageCompleted(
                    cycle_id=context.cycle_id,
                    stage_name=self.name,
                    status=StageStatus.FAIL_REJECT,
                    completed_at=now_utc(),
                )
            )
            return StageResult(
                status=StageStatus.FAIL_REJECT,
                failure_path=gate.failure_path,
                failure_reason=result.reason,
                retryable=gate.retryable,
            )

        context.emit(
            StageCompleted(
                cycle_id=context.cycle_id,
                stage_name=self.name,
                status=StageStatus.ADVANCE,
                completed_at=now_utc(),
            )
        )
        return StageResult(status=StageStatus.ADVANCE)


# ===========================================================================
# Stage 3 — Signal Extraction
# ===========================================================================


class SignalExtractionStage(Stage):
    """Stage 3: Extract Signals from Evidence.

    For each Evidence, calls SignalExtractor to produce candidate Signals.
    Applies S3-G1, S3-G3, S3-G4 gates. Failures route to Reject.
    Successful drafts transition DRAFT -> VERIFIED.
    """

    def __init__(
        self,
        extractor: SignalExtractor | None = None,
        entity_resolver: Callable[[EntityRef], Entity | None] | None = None,
    ):
        self._extractor = extractor
        self._entity_resolver = entity_resolver or (lambda ref: None)
        self._gates = STAGE_3_GATES

    @property
    def name(self) -> str:
        return "S3"

    @property
    def gates(self) -> list[Gate]:
        return self._gates

    def execute(self, context: PipelineContext) -> StageResult:
        context.emit(
            StageStarted(cycle_id=context.cycle_id, stage_name=self.name, started_at=now_utc())
        )

        if self._extractor is not None:
            for evidence in list(context.evidences):
                # Resolve entity from EntityRef
                # Per S3-G1: entity must resolve
                entity_ref = self._infer_entity_ref(evidence, context)
                if entity_ref is None:
                    # Cannot extract without an entity reference
                    context.rejected_signal_drafts.append(  # type: ignore[arg-type]
                        _StubSignalDraft(evidence.id, "no entity reference")
                    )
                    continue
                entity = self._entity_resolver(entity_ref)
                if entity is None:
                    # S3-G1 fail
                    self.route_to_failure_path(
                        context,
                        gate=self._gates[0],  # S3-G1
                        result=type("R", (), {"reason": "entity unresolved"})(),
                        object_id=evidence.id,
                        object_kind="evidence",
                    )
                    continue

                try:
                    signal_drafts = self._extractor.extract(evidence, entity)
                except Exception:
                    continue

                for draft in signal_drafts:
                    # S3-G3 (falsifiability) and S3-G4 (distinct event) checks
                    # are approximate here; the gate layer runs them.
                    # If draft passes gates, transition DRAFT -> VERIFIED.
                    if not draft.claim or len(draft.claim.strip()) < 10:
                        # S3-G3 fail
                        context.rejected_signal_drafts.append(draft)  # type: ignore[arg-type]
                        continue

                    vague = ["generally", "possibly", "maybe", "could be"]
                    if any(kw in draft.claim.lower() for kw in vague):
                        # S3-G4 fail
                        context.rejected_signal_drafts.append(draft)  # type: ignore[arg-type]
                        continue

                    # Gate checks passed; transition to VERIFIED
                    try:
                        verified = draft.verify()
                        context.signals.append(verified)
                    except Exception:
                        context.rejected_signal_drafts.append(draft)

        results = self.run_gates(context)
        first_fail = self.first_failure(results)

        if first_fail is not None:
            gate, result = first_fail
            # If the failing gate is non-retryable (S3-G2 invariant), use REJECT
            status = (
                StageStatus.FAIL_REJECT
                if not gate.retryable
                else StageStatus.FAIL_REJECT
            )
            context.emit(
                StageCompleted(
                    cycle_id=context.cycle_id,
                    stage_name=self.name,
                    status=status,
                    completed_at=now_utc(),
                )
            )
            return StageResult(
                status=status,
                failure_path=gate.failure_path,
                failure_reason=result.reason,
                retryable=gate.retryable,
            )

        context.emit(
            StageCompleted(
                cycle_id=context.cycle_id,
                stage_name=self.name,
                status=StageStatus.ADVANCE,
                completed_at=now_utc(),
            )
        )
        return StageResult(status=StageStatus.ADVANCE)

    def _infer_entity_ref(
        self, evidence: Evidence, context: PipelineContext
    ) -> EntityRef | None:
        """Infer the EntityRef for an Evidence.

        For MVP, we use the first entity in context if any. Real implementation
        would use entity-extraction from the evidence content.
        """
        if context.entities:
            e = context.entities[0]
            return EntityRef(id=e.id, kind=str(e.kind.value))
        return None


# Stub for rejected signal drafts (pre-validation placeholder).
from dataclasses import dataclass  # noqa: E402


@dataclass
class _StubSignalDraft:
    """Internal stub for a signal draft that failed pre-gate checks."""

    evidence_id: ID
    reason: str


# ===========================================================================
# Stage 4 — Research Synthesis
# ===========================================================================


class ResearchSynthesisStage(Stage):
    """Stage 4: Synthesize Research from Signals.

    For each (Entity, question) tuple, calls ResearchSynthesizer to produce
    Research. Applies S4-G1, S4-G2, S4-G3, S4-G4 gates. Failures route to
    Hold or Reject. S4-G4 produces Research but flags traceability_gaps.
    """

    def __init__(
        self,
        synthesizer: ResearchSynthesizer | None = None,
        question: str = "What does this Signal mean?",
    ):
        self._synthesizer = synthesizer
        self._question = question
        self._gates = STAGE_4_GATES

    @property
    def name(self) -> str:
        return "S4"

    @property
    def gates(self) -> list[Gate]:
        return self._gates

    def execute(self, context: PipelineContext) -> StageResult:
        context.emit(
            StageStarted(cycle_id=context.cycle_id, stage_name=self.name, started_at=now_utc())
        )

        if self._synthesizer is not None and context.signals:
            # Group signals by entity
            signals_by_entity: dict[ID, list[Signal]] = {}
            for sig in context.signals:
                signals_by_entity.setdefault(sig.entity_ref.id, []).append(sig)

            for entity_id, entity_signals in signals_by_entity.items():
                entity = next((e for e in context.entities if e.id == entity_id), None)
                if entity is None:
                    # S4-G3 fail
                    continue
                try:
                    research = self._synthesizer.synthesize(
                        entity_signals, entity, self._question
                    )
                except Exception:
                    continue
                if research.signal_ids and research.question:
                    context.research_list.append(research)
                else:
                    # S4-G1 or S4-G2 fail
                    context.rejected_signal_drafts.extend(  # type: ignore[arg-type]
                        entity_signals
                    )

        results = self.run_gates(context)
        first_fail = self.first_failure(results)

        if first_fail is not None:
            gate, result = first_fail
            status = (
                StageStatus.FAIL_HOLD
                if gate.failure_path == FailurePath.HOLD
                else StageStatus.FAIL_REJECT
            )
            context.emit(
                StageCompleted(
                    cycle_id=context.cycle_id,
                    stage_name=self.name,
                    status=status,
                    completed_at=now_utc(),
                )
            )
            return StageResult(
                status=status,
                failure_path=gate.failure_path,
                failure_reason=result.reason,
                retryable=gate.retryable,
            )

        context.emit(
            StageCompleted(
                cycle_id=context.cycle_id,
                stage_name=self.name,
                status=StageStatus.ADVANCE,
                completed_at=now_utc(),
            )
        )
        return StageResult(status=StageStatus.ADVANCE)


# ===========================================================================
# Stage 5 — Thesis Update
# ===========================================================================


class ThesisUpdateStage(Stage):
    """Stage 5: Crystallize a Thesis from Research.

    For each Research, calls ThesisCrystallizer (or applies update rules
    directly). Applies S5-G1, S5-G2, S5-G3 gates. Failures route to Hold
    or Reject.

    Per Workflow Model Rule 2, Thesis updates take 3 paths:
    - Evolve: existing Thesis modified
    - Supersede: existing Thesis replaced (history preserved)
    - Hold: inconclusive; open question annotated
    """

    def __init__(
        self,
        crystallizer: ThesisCrystallizer | None = None,
        existing_theses_provider: Callable[[ID], Thesis | None] | None = None,
    ):
        self._crystallizer = crystallizer
        self._existing_theses_provider = existing_theses_provider or (lambda eid: None)
        self._gates = STAGE_5_GATES

    @property
    def name(self) -> str:
        return "S5"

    @property
    def gates(self) -> list[Gate]:
        return self._gates

    def execute(self, context: PipelineContext) -> StageResult:
        context.emit(
            StageStarted(cycle_id=context.cycle_id, stage_name=self.name, started_at=now_utc())
        )

        for research in list(context.research_list):
            existing = self._existing_theses_provider(research.entity_ref.id)

            if self._crystallizer is not None:
                try:
                    thesis = self._crystallizer.crystallize(research, existing)
                except Exception:
                    # S5-G1 fail
                    continue
            else:
                # Without a crystallizer, we cannot produce a Thesis.
                # This is a configuration issue, not a gate failure.
                continue

            if not thesis.interpretation.strip():
                # S5-G1 fail
                continue

            if len(thesis.interpretation.strip()) < 20:
                # S5-G2 fail
                continue

            entity_ids = {e.id for e in context.entities}
            if thesis.entity_ref.id not in entity_ids:
                # S5-G3 fail
                context.held_theses.append(thesis)
                continue

            # Apply path logic per Workflow Model Rule 2
            if existing is None:
                # New Thesis (Path A: emerge -> evolving)
                context.theses.append(thesis)
            else:
                # Path decision based on whether research supports, refines,
                # or invalidates the existing Thesis.
                # For MVP: evolve if new research exists (always true here).
                try:
                    evolved = existing.evolve(
                        new_interpretation=thesis.interpretation,
                        contributing_research_ids=(research.id,),
                        by=research.id,
                    )
                    context.theses.append(evolved)
                except Exception:
                    context.theses.append(thesis)

        results = self.run_gates(context)
        first_fail = self.first_failure(results)

        if first_fail is not None:
            gate, result = first_fail
            status = (
                StageStatus.FAIL_HOLD
                if gate.failure_path == FailurePath.HOLD
                else StageStatus.FAIL_REJECT
            )
            context.emit(
                StageCompleted(
                    cycle_id=context.cycle_id,
                    stage_name=self.name,
                    status=status,
                    completed_at=now_utc(),
                )
            )
            return StageResult(
                status=status,
                failure_path=gate.failure_path,
                failure_reason=result.reason,
                retryable=gate.retryable,
            )

        context.emit(
            StageCompleted(
                cycle_id=context.cycle_id,
                stage_name=self.name,
                status=StageStatus.ADVANCE,
                completed_at=now_utc(),
            )
        )
        return StageResult(status=StageStatus.ADVANCE)


# ===========================================================================
# Stage 6 — Knowledge Update
# ===========================================================================


class KnowledgeUpdateStage(Stage):
    """Stage 6: Integrate Thesis into Knowledge.

    For each Thesis, calls KnowledgeIntegrator. Applies S6-G1, S6-G2, S6-G3
    gates. Failures route to Pending.
    """

    def __init__(self, integrator: KnowledgeIntegrator | None = None):
        self._integrator = integrator
        self._gates = STAGE_6_GATES

    @property
    def name(self) -> str:
        return "S6"

    @property
    def gates(self) -> list[Gate]:
        return self._gates

    def execute(self, context: PipelineContext) -> StageResult:
        context.emit(
            StageStarted(cycle_id=context.cycle_id, stage_name=self.name, started_at=now_utc())
        )

        for thesis in list(context.theses):
            # Maturity check (S6-G1): EMERGING -> Pending
            if thesis.status == ThesisStatus.EMERGING:
                context.theses_pending.append(thesis)
                context.theses.remove(thesis)
                continue

            # S6-G2 traceability, S6-G3 structure consistency
            # Checked by gate validators. If pass, integrate.
            try:
                if self._integrator is not None:
                    self._integrator.integrate(thesis)
            except Exception:
                context.theses_pending.append(thesis)
                context.theses.remove(thesis)
                continue

        results = self.run_gates(context)
        first_fail = self.first_failure(results)

        if first_fail is not None:
            gate, result = first_fail
            context.emit(
                StageCompleted(
                    cycle_id=context.cycle_id,
                    stage_name=self.name,
                    status=StageStatus.FAIL_PENDING,
                    completed_at=now_utc(),
                )
            )
            # Move theses to pending
            for t in context.theses:
                if t not in context.theses_pending:
                    context.theses_pending.append(t)
            context.theses.clear()
            return StageResult(
                status=StageStatus.FAIL_PENDING,
                failure_path=FailurePath.PENDING,
                failure_reason=result.reason,
                retryable=gate.retryable,
            )

        context.emit(
            StageCompleted(
                cycle_id=context.cycle_id,
                stage_name=self.name,
                status=StageStatus.ADVANCE,
                completed_at=now_utc(),
            )
        )
        return StageResult(status=StageStatus.ADVANCE)


# ===========================================================================
# Default Stage List (in pipeline order)
# ===========================================================================


def default_stages() -> list[Stage]:
    """Return the default 6-stage pipeline (no implementation interfaces).

    For testing, callers can provide their own interfaces.
    """
    return [
        SourceObservationStage(),
        EvidenceProductionStage(),
        SignalExtractionStage(),
        ResearchSynthesisStage(),
        ThesisUpdateStage(),
        KnowledgeUpdateStage(),
    ]
