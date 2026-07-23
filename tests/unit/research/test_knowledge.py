"""Tests for KnowledgeUpdater (Phase 5 Checkpoint 1)."""

import pytest

from src.core.entities import Entity, EntityKind
from src.core.evidence import Evidence, Quality
from src.core.ids import ID
from src.core.invariants import Score
from src.core.knowledge import InMemoryKnowledge
from src.core.lifecycle import ResearchStatus, SignalStatus
from src.core.research import Research
from src.core.signals import EntityRef, Signal, SignalDirection, SignalHorizon
from src.core.sources import Source, SourceType
from src.core.theses import Thesis
from src.persistence.in_memory import InMemoryStore
from src.persistence.store import Store
from src.research.knowledge import KnowledgeUpdateReport, KnowledgeUpdater


# ----------------------- helpers -----------------------


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


def _score(value: float) -> Score:
    return Score(
        magnitude=value,
        confidence=value,
        timeliness=value,
        novelty=value,
        actionability=value,
    )


def _signal(
    entity: Entity,
    *,
    status: SignalStatus = SignalStatus.VERIFIED,
    composite: float = 0.7,
    signal_id: str = "s-1",
) -> Signal:
    return Signal.create(
        entity_ref=EntityRef(id=entity.id, kind=entity.kind.value),
        type="capital_action",
        claim=f"Signal {signal_id} claim",
        evidence_ids=(ID("ev-1"),),
        direction=SignalDirection.BULLISH,
        horizon=SignalHorizon.SHORT,
        score=_score(composite),
        status=status,
        id=ID(signal_id),
    )


def _build_store() -> Store:
    store = InMemoryStore()
    entity = _entity()
    evidence = _evidence()
    store.put_entity(entity)
    store.put_evidence(evidence)
    return store


# ----------------------- dep inversion -----------------------


class TestKnowledgeUpdaterNoRuntimeInternals:
    def test_does_not_import_runtime_internals(self) -> None:
        import re

        import src.research.knowledge as mod

        source = mod.__file__ or ""
        with open(source, encoding="utf-8") as f:
            contents = f.read()
        # KnowledgeUpdater may consume OUTPUTS from runtime (CycleReport,
        # ValidationReport) but MUST NOT import runtime internals.
        # Internals are: executor, queue, scheduler, retry_manager,
        # retry_orchestrator, validator, audit, dead_letter.
        # Outputs (allowed): cycle.CycleReport, validator.ValidationReport.
        runtime_internal_patterns = [
            r"from\s+src\.runtime\.executor",
            r"from\s+src\.runtime\.queue",
            r"from\s+src\.runtime\.scheduler",
            r"from\s+src\.runtime\.retry_manager",
            r"from\s+src\.runtime\.retry_orchestrator",
            r"from\s+src\.runtime\.audit",
            r"from\s+src\.runtime\.dead_letter",
        ]
        for pat in runtime_internal_patterns:
            assert not re.search(pat, contents), f"unexpected runtime import: {pat}"

    def test_runtime_cycle_orchestrator_not_imported(self) -> None:
        """Specifically: RuntimeCycle (the orchestrator class) is internal;
        only CycleReport (the output dataclass) may be imported."""
        import re

        import src.research.knowledge as mod

        source = mod.__file__ or ""
        with open(source, encoding="utf-8") as f:
            contents = f.read()
        assert not re.search(r"from\s+src\.runtime\.cycle\s+import\s+RuntimeCycle", contents)

    def test_does_not_import_concrete_store(self) -> None:
        import re

        import src.research.knowledge as mod

        source = mod.__file__ or ""
        with open(source, encoding="utf-8") as f:
            contents = f.read()
        import_re = re.compile(
            r"^\s*(?:from\s+src\.persistence\.in_memory|import\s+src\.persistence\.in_memory)",
            re.MULTILINE,
        )
        assert not import_re.search(contents), "knowledge.py imports concrete store"


# ----------------------- read-side -----------------------


class TestKnowledgeRead:
    def test_update_reads_signals_from_store(self) -> None:
        store = _build_store()
        entity = store.get_entity(store.list_entities()[0].id) if store.list_entities() else _entity()
        # Add 3 signals.
        for i in range(3):
            store.put_signal(_signal(entity, signal_id=f"s-{i}"))
        knowledge = InMemoryKnowledge()
        updater = KnowledgeUpdater(store=store, knowledge=knowledge)
        report = updater.update()
        assert report.signals_seen == 3

    def test_update_empty_store(self) -> None:
        store = InMemoryStore()
        knowledge = InMemoryKnowledge()
        updater = KnowledgeUpdater(store=store, knowledge=knowledge)
        report = updater.update()
        assert report.signals_seen == 0
        assert report.signals_promoted == 0
        assert report.signals_demoted == 0
        assert report.signals_rejected == 0


# ----------------------- write-side: promotion -----------------------


class TestKnowledgePromotion:
    def test_promotes_verified_to_active(self) -> None:
        store = _build_store()
        entity_id = next(e.id for e in store.list_entities())
        entity = store.get_entity(entity_id)
        assert entity is not None
        sig = _signal(entity, status=SignalStatus.VERIFIED, composite=0.8, signal_id="s-promote")
        store.put_signal(sig)
        knowledge = InMemoryKnowledge()
        updater = KnowledgeUpdater(store=store, knowledge=knowledge)
        report = updater.update()
        # Signal was promoted to ACTIVE.
        assert store.get_signal(str(sig.id)).status == SignalStatus.ACTIVE
        assert report.signals_promoted == 1

    def test_demotes_active_to_decayed(self) -> None:
        """ACTIVE borderline signals decay (cannot transition to HELD)."""
        store = _build_store()
        entity_id = next(e.id for e in store.list_entities())
        entity = store.get_entity(entity_id)
        assert entity is not None
        sig = _signal(entity, status=SignalStatus.ACTIVE, composite=0.4, signal_id="s-demote")
        store.put_signal(sig)
        knowledge = InMemoryKnowledge()
        updater = KnowledgeUpdater(store=store, knowledge=knowledge)
        report = updater.update()
        assert store.get_signal(str(sig.id)).status == SignalStatus.DECAYED
        assert report.signals_demoted == 1

    def test_decays_low_active_signal(self) -> None:
        store = _build_store()
        entity_id = next(e.id for e in store.list_entities())
        entity = store.get_entity(entity_id)
        assert entity is not None
        sig = _signal(entity, status=SignalStatus.ACTIVE, composite=0.1, signal_id="s-decay")
        store.put_signal(sig)
        knowledge = InMemoryKnowledge()
        updater = KnowledgeUpdater(store=store, knowledge=knowledge)
        report = updater.update()
        assert store.get_signal(str(sig.id)).status == SignalStatus.DECAYED

    def test_rejects_low_verified_signal(self) -> None:
        store = _build_store()
        entity_id = next(e.id for e in store.list_entities())
        entity = store.get_entity(entity_id)
        assert entity is not None
        sig = _signal(entity, status=SignalStatus.VERIFIED, composite=0.1, signal_id="s-reject")
        store.put_signal(sig)
        knowledge = InMemoryKnowledge()
        updater = KnowledgeUpdater(store=store, knowledge=knowledge)
        report = updater.update()
        assert store.get_signal(str(sig.id)).status == SignalStatus.REJECTED
        assert report.signals_rejected == 1


# ----------------------- write-side: synthesis -----------------------


class TestKnowledgeSynthesis:
    def test_creates_research_for_new_entity(self) -> None:
        store = _build_store()
        entity_id = next(e.id for e in store.list_entities())
        entity = store.get_entity(entity_id)
        assert entity is not None
        # No existing research; one signal exists.
        sig = _signal(entity, status=SignalStatus.ACTIVE, composite=0.7, signal_id="s-synth")
        store.put_signal(sig)
        knowledge = InMemoryKnowledge()
        updater = KnowledgeUpdater(store=store, knowledge=knowledge)
        report = updater.update()
        assert len(report.research_synthesis.research_created) == 1

    def test_no_new_research_when_signals_empty(self) -> None:
        store = _build_store()
        knowledge = InMemoryKnowledge()
        updater = KnowledgeUpdater(store=store, knowledge=knowledge)
        report = updater.update()
        assert report.research_synthesis.research_created == ()


# ----------------------- write-side: themes -----------------------


class TestKnowledgeThemes:
    def test_evolves_thesis_when_path_a_fires(self) -> None:
        store = _build_store()
        entity_id = next(e.id for e in store.list_entities())
        entity = store.get_entity(entity_id)
        assert entity is not None
        # Existing thesis.
        thesis = Thesis.create(
            entity_ref=EntityRef(id=entity.id, kind=entity.kind.value),
            interpretation="old interpretation",
        )
        store.put_thesis(thesis)
        # Existing research with mid-significance reasoning (≥0.55).
        from src.core.research import Reasoning

        research = Research.create(
            entity_ref=EntityRef(id=entity.id, kind=entity.kind.value),
            question="Q?",
            signal_ids=(ID("s-x"),),
            reasoning=Reasoning(
                significance=0.7,
                causality=(),
                one_liner="",
            ),
        )
        store.put_research(research)
        knowledge = InMemoryKnowledge()
        updater = KnowledgeUpdater(store=store, knowledge=knowledge)
        report = updater.update()
        # Theme evolution occurred.
        assert report.theme_evolution.evolved_count >= 1


# ----------------------- integration -----------------------


class TestKnowledgeIntegration:
    def test_end_to_end_promotion_then_synthesis(self) -> None:
        """Pipeline: VERIFIED signal with high composite → ACTIVE →
        synthesizer picks it up because it's eligible (VERIFIED+ACTIVE)."""
        store = _build_store()
        entity_id = next(e.id for e in store.list_entities())
        entity = store.get_entity(entity_id)
        assert entity is not None
        sig = _signal(entity, status=SignalStatus.VERIFIED, composite=0.85, signal_id="s-e2e")
        store.put_signal(sig)
        knowledge = InMemoryKnowledge()
        updater = KnowledgeUpdater(store=store, knowledge=knowledge)
        report = updater.update()

        # After the pass:
        # - Signal was promoted to ACTIVE (in store).
        assert store.get_signal(str(sig.id)).status == SignalStatus.ACTIVE
        # - Research was created (signal was eligible).
        assert len(report.research_synthesis.research_created) == 1
        # - Knowledge accumulator was updated.
        assert knowledge.signal_count(status=SignalStatus.ACTIVE) >= 1

    def test_report_to_dict_is_json_serializable(self) -> None:
        import json

        store = _build_store()
        knowledge = InMemoryKnowledge()
        updater = KnowledgeUpdater(store=store, knowledge=knowledge)
        report = updater.update()
        json.dumps(report.to_dict())