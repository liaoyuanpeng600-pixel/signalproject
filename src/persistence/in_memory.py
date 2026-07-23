"""
In-memory persistence backend — MVP.

`InMemoryStore` is the only persistence backend for the MVP. It enforces:
- Evidence immutability: `put_evidence` raises `EvidenceAlreadyExists` if an
  Evidence with the same ID is already stored.
- OverrideRecord append-only: `append_override` always appends; records cannot
  be removed or replaced.
- Object identity: keyed by ID; the same ID always returns the same object
  (until superseded, which is a separate lifecycle event).

The store is thread-unsafe; concurrency is handled by the Runtime layer
(see docs/03_RUNTIME_MODEL.md OQ-7 for per-Thesis serialization).

Snapshot/restore uses JSON serialization via dataclasses.asdict. This is
sufficient for the MVP checkpoint mechanism; production backends will use
their own serialization.
"""

from __future__ import annotations

import copy
from dataclasses import asdict, is_dataclass
from typing import TYPE_CHECKING

from src.persistence.override import OverrideRecord
from src.persistence.store import Store

if TYPE_CHECKING:
    from src.core.entities import Entity
    from src.core.evidence import Evidence
    from src.core.research import Research
    from src.core.signals import Signal
    from src.core.sources import Source
    from src.core.theses import Thesis


class PersistenceError(Exception):
    """Base class for persistence-layer errors."""


class EvidenceAlreadyExists(PersistenceError):
    """Raised when attempting to overwrite an existing Evidence record.

    Evidence is write-once (immutable). To correct Evidence, produce a new
    Evidence object linked to the original via a correction Signal.
    """

    def __init__(self, evidence_id: str) -> None:
        self.evidence_id = evidence_id
        super().__init__(
            f"Evidence {evidence_id!r} already exists; Evidence is immutable. "
            "Produce a new Evidence and link via a correction Signal."
        )


class InMemoryStore(Store):
    """In-memory persistence backend (MVP).

    Stores Objects in plain dicts keyed by ID. All public methods are O(1)
    except `list_*`, which return tuples over the stored values.

    Thread-safety: NOT thread-safe. The Runtime layer is responsible for
    serializing concurrent access (per docs/03_RUNTIME_MODEL.md OQ-7).
    """

    def __init__(self) -> None:
        self._entities: dict[str, "Entity"] = {}
        self._sources: dict[str, "Source"] = {}
        self._evidence: dict[str, "Evidence"] = {}
        self._signals: dict[str, "Signal"] = {}
        self._research: dict[str, "Research"] = {}
        self._theses: dict[str, "Thesis"] = {}
        self._overrides: list["OverrideRecord"] = []

    # ---- Entities ----

    def put_entity(self, entity: "Entity") -> None:
        self._entities[str(entity.id)] = entity

    def get_entity(self, entity_id: str) -> "Entity | None":
        return self._entities.get(entity_id)

    def list_entities(self) -> tuple["Entity", ...]:
        return tuple(self._entities.values())

    # ---- Sources ----

    def put_source(self, source: "Source") -> None:
        self._sources[str(source.id)] = source

    def get_source(self, source_id: str) -> "Source | None":
        return self._sources.get(source_id)

    def list_sources(self) -> tuple["Source", ...]:
        return tuple(self._sources.values())

    # ---- Evidence (immutable) ----

    def put_evidence(self, evidence: "Evidence") -> None:
        eid = str(evidence.id)
        if eid in self._evidence:
            raise EvidenceAlreadyExists(eid)
        self._evidence[eid] = evidence

    def get_evidence(self, evidence_id: str) -> "Evidence | None":
        return self._evidence.get(evidence_id)

    def list_evidence(self) -> tuple["Evidence", ...]:
        return tuple(self._evidence.values())

    # ---- Signals ----

    def put_signal(self, signal: "Signal") -> None:
        self._signals[str(signal.id)] = signal

    def get_signal(self, signal_id: str) -> "Signal | None":
        return self._signals.get(signal_id)

    def list_signals(self) -> tuple["Signal", ...]:
        return tuple(self._signals.values())

    # ---- Research ----

    def put_research(self, research: "Research") -> None:
        self._research[str(research.id)] = research

    def get_research(self, research_id: str) -> "Research | None":
        return self._research.get(research_id)

    def list_research(self) -> tuple["Research", ...]:
        return tuple(self._research.values())

    # ---- Theses ----

    def put_thesis(self, thesis: "Thesis") -> None:
        self._theses[str(thesis.id)] = thesis

    def get_thesis(self, thesis_id: str) -> "Thesis | None":
        return self._theses.get(thesis_id)

    def list_theses(self) -> tuple["Thesis", ...]:
        return tuple(self._theses.values())

    # ---- Override Records (append-only) ----

    def append_override(self, record: "OverrideRecord") -> None:
        self._overrides.append(record)

    def list_overrides(self, target_id: str | None = None) -> tuple["OverrideRecord", ...]:
        if target_id is None:
            return tuple(self._overrides)
        return tuple(r for r in self._overrides if str(r.target_id) == target_id)

    # ---- Bulk operations ----

    def clear(self) -> None:
        """Remove all stored objects. Primarily for tests."""
        self._entities.clear()
        self._sources.clear()
        self._evidence.clear()
        self._signals.clear()
        self._research.clear()
        self._theses.clear()
        self._overrides.clear()

    def snapshot(self) -> dict[str, object]:
        """Return a JSON-serializable snapshot of all stored objects.

        Snapshot is a deep copy so the caller can mutate it freely.
        """
        return _serialize_snapshot(
            entities=self._entities,
            sources=self._sources,
            evidence=self._evidence,
            signals=self._signals,
            research=self._research,
            theses=self._theses,
            overrides=self._overrides,
        )

    def restore(self, snapshot: dict[str, object]) -> None:
        """Replace store contents from a snapshot. Used by checkpoint restore.

        Validates the snapshot shape minimally; callers should pass snapshots
        produced by `snapshot()` to guarantee structural compatibility.
        """
        self.clear()
        _deserialize_snapshot(snapshot, store=self)


def _serialize_snapshot(
    *,
    entities: dict[str, object],
    sources: dict[str, object],
    evidence: dict[str, object],
    signals: dict[str, object],
    research: dict[str, object],
    theses: dict[str, object],
    overrides: list[object],
) -> dict[str, object]:
    """Convert dataclass instances to JSON-serializable dicts.

    Enum values are converted to their `.value` strings; tuples stay as lists.
    """
    return {
        "entities": {k: _to_dict(v) for k, v in entities.items()},
        "sources": {k: _to_dict(v) for k, v in sources.items()},
        "evidence": {k: _to_dict(v) for k, v in evidence.items()},
        "signals": {k: _to_dict(v) for k, v in signals.items()},
        "research": {k: _to_dict(v) for k, v in research.items()},
        "theses": {k: _to_dict(v) for k, v in theses.items()},
        "overrides": [_to_dict(r) for r in overrides],
    }


def _to_dict(obj: object) -> object:
    """Convert a dataclass to a JSON-serializable dict.

    Uses deepcopy so the snapshot is independent of the live store.
    """
    if is_dataclass(obj) and not isinstance(obj, type):
        raw = asdict(obj)
        return _convert_values(raw)
    return copy.deepcopy(obj)


def _convert_values(value: object) -> object:
    """Recursively convert enums to strings and tuples to lists for JSON."""
    # Lazy import to avoid cycle at module load.
    from enum import Enum

    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {k: _convert_values(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_convert_values(v) for v in value]
    return value


def _deserialize_snapshot(snapshot: dict[str, object], store: InMemoryStore) -> None:
    """Load dataclass instances from a snapshot dict and insert into the store.

    Conversion is by type lookup (key -> dataclass class). Unknown types raise
    PersistenceError so a malformed snapshot is loud, not silent.
    """
    from src.core.entities import Entity, EntityKind, EntityStatus
    from src.core.evidence import Evidence, Quality, SourceType as EvidenceSourceType
    from src.core.research import Research
    from src.core.signals import (
        EntityRef,
        Metadata,
        Signal,
        SignalDirection,
        SignalHorizon,
        SignalStatus,
    )
    from src.core.sources import Source, SourceStatus, SourceType
    from src.core.theses import Thesis

    try:
        entity_map: dict[str, dict[str, object]] = snapshot["entities"]  # type: ignore[index]
        source_map: dict[str, dict[str, object]] = snapshot["sources"]  # type: ignore[index]
        evidence_map: dict[str, dict[str, object]] = snapshot["evidence"]  # type: ignore[index]
        signal_map: dict[str, dict[str, object]] = snapshot["signals"]  # type: ignore[index]
        research_map: dict[str, dict[str, object]] = snapshot["research"]  # type: ignore[index]
        thesis_map: dict[str, dict[str, object]] = snapshot["theses"]  # type: ignore[index]
        override_list: list[dict[str, object]] = snapshot["overrides"]  # type: ignore[index]
    except KeyError as exc:
        raise PersistenceError(f"Invalid snapshot: missing key {exc}") from exc

    for d in entity_map.values():
        store.put_entity(
            Entity(
                id=d["id"],  # type: ignore[arg-type]
                kind=EntityKind(d["kind"]),  # type: ignore[arg-type]
                name=d["name"],  # type: ignore[arg-type]
                aliases=tuple(d.get("aliases", ())),  # type: ignore[arg-type]
                status=EntityStatus(d.get("status", EntityStatus.ACTIVE.value)),  # type: ignore[arg-type]
                classification=dict(d.get("classification", {})),  # type: ignore[arg-type]
            )
        )

    for d in source_map.values():
        store.put_source(
            Source(
                id=d["id"],  # type: ignore[arg-type]
                type=SourceType(d["type"]),  # type: ignore[arg-type]
                url=d["url"],  # type: ignore[arg-type]
                name=d["name"],  # type: ignore[arg-type]
                status=d.get("status", SourceStatus.ACTIVE.value),  # type: ignore[arg-type]
                reliability_score=float(d.get("reliability_score", 1.0)),  # type: ignore[arg-type]
                activated_at=d.get("activated_at", ""),  # type: ignore[arg-type]
                last_observed_at=d.get("last_observed_at"),  # type: ignore[arg-type]
                health_notes=tuple(d.get("health_notes", ())),  # type: ignore[arg-type]
            )
        )

    for d in evidence_map.values():
        quality_d = d.get("quality", {})  # type: ignore[union-attr]
        store.put_evidence(
            Evidence(
                id=d["id"],  # type: ignore[arg-type]
                source_ids=tuple(d["source_ids"]),  # type: ignore[arg-type]
                content=d["content"],  # type: ignore[arg-type]
                quality=Quality(
                    source_reliability=float(quality_d["source_reliability"]),  # type: ignore[arg-type]
                    content_completeness=float(quality_d["content_completeness"]),  # type: ignore[arg-type]
                    retrieval_confidence=float(quality_d["retrieval_confidence"]),  # type: ignore[arg-type]
                ),
                retrieved_at=d.get("retrieved_at", ""),  # type: ignore[arg-type]
                retrievable=bool(d.get("retrievable", True)),  # type: ignore[arg-type]
                source_type=EvidenceSourceType(d["source_type"]) if d.get("source_type") else None,  # type: ignore[arg-type]
                char_offset=tuple(d["char_offset"]) if d.get("char_offset") else None,  # type: ignore[arg-type]
                excerpt=d.get("excerpt"),  # type: ignore[arg-type]
                document_hash=d.get("document_hash"),  # type: ignore[arg-type]
            )
        )

    for d in signal_map.values():
        entity_ref_d = d["entity_ref"]  # type: ignore[index]
        score_d = d["score"]  # type: ignore[index]
        metadata_d = d.get("metadata", {})  # type: ignore[arg-type]
        from src.core.invariants import Score

        store.put_signal(
            Signal(
                id=d["id"],  # type: ignore[arg-type]
                entity_ref=EntityRef(
                    id=entity_ref_d["id"],  # type: ignore[arg-type]
                    kind=entity_ref_d["kind"],  # type: ignore[arg-type]
                ),
                type=d["type"],  # type: ignore[arg-type]
                claim=d["claim"],  # type: ignore[arg-type]
                evidence_ids=tuple(d["evidence_ids"]),  # type: ignore[arg-type]
                direction=SignalDirection(d["direction"]),  # type: ignore[arg-type]
                horizon=SignalHorizon(d["horizon"]),  # type: ignore[arg-type]
                score=Score(
                    magnitude=float(score_d["magnitude"]),  # type: ignore[arg-type]
                    confidence=float(score_d["confidence"]),  # type: ignore[arg-type]
                    timeliness=float(score_d["timeliness"]),  # type: ignore[arg-type]
                    novelty=float(score_d["novelty"]),  # type: ignore[arg-type]
                    actionability=float(score_d["actionability"]),  # type: ignore[arg-type]
                ),
                status=SignalStatus(d.get("status", SignalStatus.DRAFT.value)),  # type: ignore[arg-type]
                timestamp=d.get("timestamp", ""),  # type: ignore[arg-type]
                detected_at=d.get("detected_at", ""),  # type: ignore[arg-type]
                cluster_id=d.get("cluster_id"),  # type: ignore[arg-type]
                metadata=Metadata(
                    source_doc_id=metadata_d.get("source_doc_id"),  # type: ignore[arg-type]
                    cluster_size=metadata_d.get("cluster_size"),  # type: ignore[arg-type]
                    burst_triggered=bool(metadata_d.get("burst_triggered", False)),  # type: ignore[arg-type]
                    reasoning_skipped=bool(metadata_d.get("reasoning_skipped", False)),  # type: ignore[arg-type]
                    reasoning_partial=bool(metadata_d.get("reasoning_partial", False)),  # type: ignore[arg-type]
                    score_partial=bool(metadata_d.get("score_partial", False)),  # type: ignore[arg-type]
                    degrade_mode=bool(metadata_d.get("degrade_mode", False)),  # type: ignore[arg-type]
                    override_active=bool(metadata_d.get("override_active", False)),  # type: ignore[arg-type]
                    precedent_basis=metadata_d.get("precedent_basis"),  # type: ignore[arg-type]
                    precedent_conflict=bool(metadata_d.get("precedent_conflict", False)),  # type: ignore[arg-type]
                    custom_tags=tuple(metadata_d.get("custom_tags", ())),  # type: ignore[arg-type]
                ),
                provenance_present=bool(d.get("provenance_present", True)),  # type: ignore[arg-type]
            )
        )

    for d in research_map.values():
        # Research uses ResearchStatus as a str Enum; reconstruct via enum class.
        from src.core.research import ResearchStatus

        reasoning_d = d.get("reasoning")
        reasoning = None
        if reasoning_d:
            from src.core.research import (
                CausalLink,
                Durability,
                PrecedentRef,
                Reasoning,
                Reversibility,
            )

            reasoning = Reasoning(
                significance=float(reasoning_d["significance"]),  # type: ignore[arg-type]
                causality=tuple(
                    CausalLink(
                        to_entity=EntityRef(
                            id=cl["to_entity"]["id"],  # type: ignore[arg-type]
                            kind=cl["to_entity"]["kind"],  # type: ignore[arg-type]
                        ),
                        mechanism=cl["mechanism"],  # type: ignore[arg-type]
                        likelihood=cl["likelihood"],  # type: ignore[arg-type]
                        time_horizon=SignalHorizon(cl["time_horizon"]),  # type: ignore[arg-type]
                    )
                    for cl in reasoning_d.get("causality", [])
                ),
                durability=Durability(reasoning_d.get("durability", Durability.SHORT.value)),  # type: ignore[arg-type]
                reversibility=Reversibility(
                    reasoning_d.get("reversibility", Reversibility.EASY.value)  # type: ignore[arg-type]
                ),
                precedents=tuple(
                    PrecedentRef(
                        signal_id=p["signal_id"],  # type: ignore[arg-type]
                        similarity=float(p["similarity"]),  # type: ignore[arg-type]
                        outcome=p["outcome"],  # type: ignore[arg-type]
                    )
                    for p in reasoning_d.get("precedents", [])
                ),
                one_liner=reasoning_d.get("one_liner", ""),  # type: ignore[arg-type]
            )

        store.put_research(
            Research(
                id=d["id"],  # type: ignore[arg-type]
                entity_ref=EntityRef(
                    id=d["entity_ref"]["id"],  # type: ignore[arg-type]
                    kind=d["entity_ref"]["kind"],  # type: ignore[arg-type]
                ),
                question=d["question"],  # type: ignore[arg-type]
                signal_ids=tuple(d["signal_ids"]),  # type: ignore[arg-type]
                status=ResearchStatus(d.get("status", ResearchStatus.OPEN.value)),  # type: ignore[arg-type]
                opened_at=d.get("opened_at", ""),  # type: ignore[arg-type]
                concluded_at=d.get("concluded_at"),  # type: ignore[arg-type]
                reasoning=reasoning,
                traceability_gaps=bool(d.get("traceability_gaps", False)),  # type: ignore[arg-type]
                held_reason=d.get("held_reason"),  # type: ignore[arg-type]
            )
        )

    for d in thesis_map.values():
        from src.core.theses import ThesisEvolution, ThesisStatus

        evolutions = tuple(
            ThesisEvolution(
                at=e["at"],  # type: ignore[arg-type]
                by=e["by"],  # type: ignore[arg-type]
                kind=e["kind"],  # type: ignore[arg-type]
                prior_interpretation=e["prior_interpretation"],  # type: ignore[arg-type]
                new_interpretation=e["new_interpretation"],  # type: ignore[arg-type]
                contributing_research_ids=tuple(e.get("contributing_research_ids", ())),  # type: ignore[arg-type]
                rationale=e.get("rationale", ""),  # type: ignore[arg-type]
            )
            for e in d.get("evolution_history", [])
        )

        store.put_thesis(
            Thesis(
                id=d["id"],  # type: ignore[arg-type]
                entity_ref=EntityRef(
                    id=d["entity_ref"]["id"],  # type: ignore[arg-type]
                    kind=d["entity_ref"]["kind"],  # type: ignore[arg-type]
                ),
                interpretation=d["interpretation"],  # type: ignore[arg-type]
                status=ThesisStatus(d.get("status", ThesisStatus.EMERGING.value)),  # type: ignore[arg-type]
                supporting_research_ids=tuple(d.get("supporting_research_ids", ())),  # type: ignore[arg-type]
                evolution_history=evolutions,
                created_at=d.get("created_at", ""),  # type: ignore[arg-type]
                open_questions=tuple(d.get("open_questions", ())),  # type: ignore[arg-type]
            )
        )

    for d in override_list:
        from src.persistence.override import OverrideAction

        store.append_override(
            OverrideRecord(
                id=d["id"],  # type: ignore[arg-type]
                target_id=d["target_id"],  # type: ignore[arg-type]
                action=OverrideAction(d["action"]),  # type: ignore[arg-type]
                rationale=d["rationale"],  # type: ignore[arg-type]
                actor=d["actor"],  # type: ignore[arg-type]
                at=d["at"],  # type: ignore[arg-type]
                payload=dict(d.get("payload") or {}),  # type: ignore[arg-type]
            )
        )