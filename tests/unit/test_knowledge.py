"""Tests for the Knowledge module."""

from src.core.entities import Entity, EntityKind
from src.core.evidence import Evidence, Quality
from src.core.ids import new_id
from src.core.knowledge import InMemoryKnowledge, KnowledgeAccumulator
from src.core.research import Research
from src.core.signals import EntityRef, Signal, SignalDirection, SignalHorizon, SignalStatus
from src.core.theses import Thesis, ThesisStatus
from src.core.invariants import Score


def make_signal(status: SignalStatus = SignalStatus.ACTIVE) -> Signal:
    return Signal.create(
        entity_ref=EntityRef(id="entity-1", kind="company"),
        type="earnings",
        claim="ACME reported EPS.",
        evidence_ids=("ev-1",),
        direction=SignalDirection.BULLISH,
        horizon=SignalHorizon.SHORT,
        score=Score(0.7, 0.9, 0.8, 0.6, 0.75),
        status=status,
    )


def make_research() -> Research:
    return Research.create(
        entity_ref=EntityRef(id="entity-1", kind="company"),
        question="Is ACME undervalued?",
        signal_ids=("sig-1",),
    )


def make_thesis() -> Thesis:
    return Thesis.create(
        entity_ref=EntityRef(id="entity-1", kind="company"),
        interpretation="ACME is undervalued.",
    )


def make_evidence() -> Evidence:
    return Evidence.create(
        source_ids=("source-1",),
        content="ACME content.",
        quality=Quality(0.9, 0.9, 0.9),
    )


class TestInMemoryKnowledgeIsAccumulator:
    def test_implements_interface(self) -> None:
        knowledge = InMemoryKnowledge()
        assert isinstance(knowledge, KnowledgeAccumulator)


class TestAddSignals:
    def test_add_and_retrieve(self) -> None:
        knowledge = InMemoryKnowledge()
        signal = make_signal()
        knowledge.add_signal(signal)
        result = knowledge.get_active_signals_for_entity(EntityRef(id="entity-1", kind="company").id)
        assert signal in result

    def test_only_active_signals_returned(self) -> None:
        knowledge = InMemoryKnowledge()
        active_signal = make_signal(SignalStatus.ACTIVE)
        draft_signal = make_signal(SignalStatus.DRAFT)
        knowledge.add_signal(active_signal)
        knowledge.add_signal(draft_signal)
        result = knowledge.get_active_signals_for_entity("entity-1")
        assert active_signal in result
        assert draft_signal not in result

    def test_active_count(self) -> None:
        knowledge = InMemoryKnowledge()
        knowledge.add_signal(make_signal(SignalStatus.ACTIVE))
        knowledge.add_signal(make_signal(SignalStatus.DRAFT))
        knowledge.add_signal(make_signal(SignalStatus.VERIFIED))
        assert knowledge.signal_count(SignalStatus.ACTIVE) == 1
        assert knowledge.signal_count(SignalStatus.DRAFT) == 1
        assert knowledge.signal_count() == 3


class TestAddResearch:
    def test_add_and_retrieve(self) -> None:
        knowledge = InMemoryKnowledge()
        research = make_research()
        knowledge.add_research(research)
        result = knowledge.get_research_for_entity("entity-1")
        assert research in result


class TestAddThesis:
    def test_add_and_retrieve(self) -> None:
        knowledge = InMemoryKnowledge()
        thesis = make_thesis()
        knowledge.add_thesis(thesis)
        result = knowledge.get_theses_for_entity("entity-1")
        assert thesis in result

    def test_multiple_theses_same_entity(self) -> None:
        knowledge = InMemoryKnowledge()
        t1 = make_thesis()
        t2 = Thesis.create(
            entity_ref=EntityRef(id="entity-1", kind="company"),
            interpretation="ACME fairly valued.",
        )
        knowledge.add_thesis(t1)
        knowledge.add_thesis(t2)
        result = knowledge.get_theses_for_entity("entity-1")
        assert len(result) == 2

    def test_thesis_count(self) -> None:
        knowledge = InMemoryKnowledge()
        knowledge.add_thesis(make_thesis())
        knowledge.add_thesis(make_thesis())
        assert knowledge.thesis_count() == 2


class TestAddEvidence:
    def test_add_evidence(self) -> None:
        knowledge = InMemoryKnowledge()
        evidence = make_evidence()
        knowledge.add_evidence(evidence)
        assert knowledge.evidence_count() == 1

    def test_link_evidence_to_signal(self) -> None:
        knowledge = InMemoryKnowledge()
        signal = make_signal()
        evidence = make_evidence()
        knowledge.add_signal(signal)
        knowledge.add_evidence(evidence)
        knowledge.link_evidence_to_signal(signal.id, evidence.id)
        result = knowledge.get_evidence_for_signal(signal.id)
        assert evidence in result


class TestEntityTracking:
    def test_add_and_retrieve_entities(self) -> None:
        knowledge = InMemoryKnowledge()
        entity = Entity.create(kind=EntityKind.COMPANY, name="ACME Corp")
        knowledge.add_entity(entity)
        entities = list(knowledge.get_all_entities())
        assert entity in entities


class TestKnowledgeAccumulation:
    def test_multiple_object_types_for_same_entity(self) -> None:
        knowledge = InMemoryKnowledge()
        entity_id = "entity-1"
        # Add various objects for the same entity
        knowledge.add_signal(make_signal())
        knowledge.add_research(make_research())
        knowledge.add_thesis(make_thesis())
        knowledge.add_evidence(make_evidence())

        assert len(knowledge.get_active_signals_for_entity(entity_id)) == 1
        assert len(knowledge.get_research_for_entity(entity_id)) == 1
        assert len(knowledge.get_theses_for_entity(entity_id)) == 1
        assert knowledge.evidence_count() == 1


class TestIDIndependence:
    def test_unique_ids(self) -> None:
        id1 = new_id()
        id2 = new_id()
        assert id1 != id2
