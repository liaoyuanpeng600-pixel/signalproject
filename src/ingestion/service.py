"""Minimal deterministic handoff orchestration for Phase 7.1.5."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from src.core.ids import ID
from src.core.sources import Source
from src.ingestion.connector import Connector
from src.ingestion.deduplication import DeduplicationResult, deduplicate_documents
from src.ingestion.models import CollectionBatch, IngestionCheckpoint
from src.ingestion.work import (
    CollectionWorkItem,
    DocumentProcessingWorkItem,
    ResearchWorkItem,
)

HANDOFF_VERSION = "handoff-v1"


def _stable_key(kind: str, *parts: object) -> str:
    payload = "\0".join((HANDOFF_VERSION, kind, *(str(part) for part in parts)))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class CollectionRunResult:
    """Connector result plus deterministic downstream document work."""

    collection_work_item: CollectionWorkItem
    batch: CollectionBatch
    deduplication: DeduplicationResult
    document_work_items: tuple[DocumentProcessingWorkItem, ...]


class CollectionRunner:
    """Coordinate application contracts without persistence or domain mutation."""

    def prepare_collection_work(
        self,
        *,
        connector: Connector,
        source: Source,
        checkpoint: IngestionCheckpoint | None = None,
        limit: int = 100,
    ) -> CollectionWorkItem:
        cursor = checkpoint.cursor if checkpoint is not None else ""
        revision = checkpoint.revision if checkpoint is not None else "new"
        key = _stable_key(
            "collection",
            source.id,
            connector.name,
            connector.version,
            cursor,
            revision,
            limit,
        )
        return CollectionWorkItem(
            id=f"work_{key}",
            source_id=source.id,
            connector_name=connector.name,
            connector_version=connector.version,
            checkpoint=checkpoint,
            limit=limit,
            idempotency_key=f"collection:{key}",
        )

    def collect(
        self,
        *,
        connector: Connector,
        source: Source,
        work_item: CollectionWorkItem,
        known_document_ids: frozenset[ID] = frozenset(),
    ) -> CollectionRunResult:
        if work_item.source_id != source.id:
            raise ValueError("CollectionWorkItem belongs to another Source")
        if (
            work_item.connector_name != connector.name
            or work_item.connector_version != connector.version
        ):
            raise ValueError("CollectionWorkItem belongs to another Connector")
        batch = connector.collect(
            source,
            work_item.checkpoint,
            work_item.limit,
        )
        deduplication = deduplicate_documents(
            batch.records,
            known_document_ids=known_document_ids,
        )
        document_work = tuple(
            self._document_work(document.id)
            for document in deduplication.accepted
        )
        return CollectionRunResult(
            collection_work_item=work_item,
            batch=batch,
            deduplication=deduplication,
            document_work_items=document_work,
        )

    def prepare_research_work(
        self,
        *,
        entity_id: ID,
        eligible_signal_ids: tuple[ID, ...],
        topic_key: str,
        policy_version: str,
    ) -> ResearchWorkItem:
        """Prepare work only after upstream Evidence/Signal eligibility.

        Signal objects are deliberately not imported. The caller at the
        existing research boundary supplies IDs that have already passed the
        canonical Evidence grounding and Signal promotion path.
        """
        normalized_signals = tuple(
            sorted(set(eligible_signal_ids), key=str)
        )
        if not normalized_signals:
            raise ValueError("At least one eligible Signal ID is required")
        if not policy_version:
            raise ValueError("policy_version is required")
        key = _stable_key(
            "research",
            entity_id,
            topic_key,
            policy_version,
            *normalized_signals,
        )
        return ResearchWorkItem(
            id=f"work_{key}",
            entity_id=entity_id,
            signal_ids=normalized_signals,
            topic_key=topic_key,
            idempotency_key=f"research:{key}",
        )

    @staticmethod
    def _document_work(document_id: ID) -> DocumentProcessingWorkItem:
        key = _stable_key("document", document_id)
        return DocumentProcessingWorkItem(
            id=f"work_{key}",
            raw_document_id=document_id,
            idempotency_key=f"document:{key}",
        )
