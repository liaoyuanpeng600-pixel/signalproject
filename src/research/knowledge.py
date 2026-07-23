"""
Knowledge graph updates — Phase 5 Checkpoint 1.

`KnowledgeUpdater` is the top-level orchestration point for the Research
layer. It consumes Runtime outputs (CycleReport, ValidationReport) and:

1. Reads ACTIVE Signals from the abstract `Store` interface.
2. Runs `ResearchSynthesizer` to aggregate Signals into Research.
3. Runs `ThemeEvolver` to evolve/supersede/hold Theses.
4. Runs `SignalPromoter` to determine Signal transitions.
5. Persists all outputs via `persistence.lifecycle` helpers.
6. Updates the `KnowledgeAccumulator`.

Dependency rules:
- Depends ONLY on `persistence.store.Store` (abstract interface).
- Consumes Runtime OUTPUTS (CycleReport, ValidationReport) only.
- Does NOT import runtime internals (executor, scheduler, retry).
- Does NOT implement curator actions (deferred to next checkpoint).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from src.core.knowledge import KnowledgeAccumulator
from src.core.lifecycle import SignalStatus
from src.core.research import Research
from src.core.signals import Signal
from src.core.theses import Thesis
from src.persistence import lifecycle as lifecycle_helpers
from src.research.promotion import PromotionDecision, SignalPromoter
from src.research.synthesis import ResearchSynthesizer, SynthesisReport
from src.research.themes import ThemeEvolutionReport, ThemeEvolver

if TYPE_CHECKING:
    from src.persistence.store import Store
    from src.runtime.cycle import CycleReport
    from src.runtime.validator import ValidationReport


@dataclass(frozen=True, slots=True)
class KnowledgeUpdateReport:
    """Outcome of one KnowledgeUpdater pass."""

    signals_seen: int
    signals_promoted: int
    signals_demoted: int
    signals_rejected: int
    research_synthesis: SynthesisReport
    theme_evolution: ThemeEvolutionReport
    cycle_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "cycle_id": self.cycle_id,
            "signals_seen": self.signals_seen,
            "signals_promoted": self.signals_promoted,
            "signals_demoted": self.signals_demoted,
            "signals_rejected": self.signals_rejected,
            "research_synthesis": {
                "created": list(self.research_synthesis.research_created),
                "updated": list(self.research_synthesis.research_updated),
                "concluded": list(self.research_synthesis.research_concluded),
            },
            "theme_evolution": {
                "evolved": self.theme_evolution.evolved_count,
                "superseded": self.theme_evolution.superseded_count,
                "held": self.theme_evolution.held_count,
            },
        }


class KnowledgeUpdater:
    """Top-level Research-layer orchestration.

    Args:
        store: Abstract persistence interface (Phase 4 `Store`).
        knowledge: KnowledgeAccumulator (Phase 1 InMemoryKnowledge or
            Phase 4 persistent variant).
        synthesizer: ResearchSynthesizer (defaults to a fresh instance).
        theme_evolver: ThemeEvolver (defaults to a fresh instance).
        promoter: SignalPromoter (defaults to a fresh instance).
    """

    def __init__(
        self,
        *,
        store: "Store",
        knowledge: KnowledgeAccumulator,
        synthesizer: ResearchSynthesizer | None = None,
        theme_evolver: ThemeEvolver | None = None,
        promoter: SignalPromoter | None = None,
    ) -> None:
        self._store = store
        self._knowledge = knowledge
        self._synthesizer = synthesizer or ResearchSynthesizer()
        self._theme_evolver = theme_evolver or ThemeEvolver()
        self._promoter = promoter or SignalPromoter()

    @property
    def store(self) -> "Store":
        return self._store

    @property
    def knowledge(self) -> KnowledgeAccumulator:
        return self._knowledge

    def update(
        self,
        *,
        cycle_report: "CycleReport | None" = None,
        validation_report: "ValidationReport | None" = None,
    ) -> KnowledgeUpdateReport:
        """Execute one knowledge-update pass.

        Steps:
            1. Read VERIFIED + ACTIVE Signals from the Store.
            2. Read existing Research from the Store.
            3. Synthesize: aggregate Signals into Research.
            4. Evolve themes: apply Path A/B/C decisions.
            5. Promote/demote Signals per policy.
            6. Persist all changes via lifecycle helpers and Store.put_*.
            7. Update the KnowledgeAccumulator.

        Args:
            cycle_report: Optional RuntimeCycle output. Currently used for
                the report's `cycle_id` field only; the updater does not
                depend on cycle_report's structure beyond that.
            validation_report: Optional Validator output. Currently unused
                by this checkpoint; reserved for future gate-aware logic.

        Returns:
            A `KnowledgeUpdateReport` summarizing the pass.
        """
        # Step 1: read eligible signals.
        all_signals = self._store.list_signals()
        eligible = tuple(
            s for s in all_signals if s.status in {SignalStatus.VERIFIED, SignalStatus.ACTIVE}
        )

        # Step 2: read existing research.
        existing_research = self._store.list_research()

        # Step 3: synthesize.
        synthesis = self._synthesizer.synthesize(
            signals=eligible,
            existing_research=existing_research,
        )

        # Step 4: theme evolution. For each (entity, research) pair, look
        # up existing Thesis and apply Path decision.
        existing_theses = self._store.list_theses()
        pairs: list[tuple[Research | None, Thesis | None]] = []
        for research in existing_research:
            thesis = self._find_thesis_for_entity(
                existing_theses, research.entity_ref.id
            )
            pairs.append((research, thesis))
        theme_report = self._theme_evolver.evolve_many(pairs=pairs)

        # Step 5: promote / demote.
        decisions = self._promoter.evaluate_many(all_signals)

        # Step 6: persist decisions. We translate each decision into a
        # lifecycle method call and persist the resulting Signal.
        promoted = 0
        demoted = 0
        rejected = 0
        for decision in decisions:
            if not decision.should_transition:
                continue
            new_signal = self._apply_decision(decision)
            self._store.put_signal(new_signal)
            if decision.target in {SignalStatus.ACTIVE}:
                promoted += 1
            elif decision.target in {SignalStatus.DECAYED, SignalStatus.HELD}:
                demoted += 1
            elif decision.target == SignalStatus.REJECTED:
                rejected += 1

        # Step 7: update KnowledgeAccumulator from the post-update Store
        # state (so promotion/demotion transitions are reflected).
        for sig in self._store.list_signals():
            self._knowledge.add_signal(sig)
        for r in self._store.list_research():
            self._knowledge.add_research(r)
        for thesis in self._store.list_theses():
            self._knowledge.add_thesis(thesis)

        return KnowledgeUpdateReport(
            signals_seen=len(all_signals),
            signals_promoted=promoted,
            signals_demoted=demoted,
            signals_rejected=rejected,
            research_synthesis=synthesis,
            theme_evolution=theme_report,
            cycle_id=str(cycle_report.cycle_id) if cycle_report is not None else None,
        )

    # ---- internals ----

    @staticmethod
    def _find_thesis_for_entity(
        theses: tuple[Thesis, ...],
        entity_id: object,
    ) -> Thesis | None:
        """Find the latest non-terminal Thesis for an entity."""
        candidates = [
            t for t in theses
            if str(t.entity_ref.id) == str(entity_id)
            and t.status.value not in {"superseded", "retired"}
        ]
        if not candidates:
            return None
        # Latest = max created_at lexicographically (ISO8601 UTC is sortable).
        return max(candidates, key=lambda t: t.created_at)

    @staticmethod
    def _apply_decision(decision: PromotionDecision) -> Signal:
        """Translate a PromotionDecision into a lifecycle-method call.

        Handles each starting status (VERIFIED, ACTIVE, HELD) and the
        corresponding target. Stays within the allowed transition graph.
        """
        sig = decision.original
        target = decision.target

        if target == SignalStatus.ACTIVE:
            if sig.status == SignalStatus.VERIFIED:
                return sig.activate()
            return sig
        if target == SignalStatus.HELD:
            if sig.status in {SignalStatus.VERIFIED, SignalStatus.ACTIVE}:
                return sig.hold()
            return sig
        if target == SignalStatus.DECAYED:
            if sig.status == SignalStatus.ACTIVE:
                return sig.decay()
            return sig
        if target == SignalStatus.REJECTED:
            if sig.status == SignalStatus.VERIFIED:
                return sig.reject()
            return sig
        return sig


__all__ = ["KnowledgeUpdateReport", "KnowledgeUpdater"]