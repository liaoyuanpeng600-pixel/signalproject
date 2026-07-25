"""Deterministic, persistence-independent ingestion identities."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import hashlib
import unicodedata

from src.core.ids import ID
from src.ingestion.models import RawDocument

NORMALIZATION_VERSION = "text-v1"
IDENTITY_VERSION = "collection-v1"


def normalize_content(content: str) -> str:
    """Return canonical text without interpreting its research meaning."""
    normalized = unicodedata.normalize("NFC", content)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in normalized.split("\n")).strip()


def content_hash(content: str) -> str:
    payload = f"{NORMALIZATION_VERSION}\0{normalize_content(content)}".encode(
        "utf-8"
    )
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def collection_identity(source_id: ID, external_id: str) -> str:
    if not source_id:
        raise ValueError("source_id is required")
    normalized_external_id = external_id.strip()
    if not normalized_external_id:
        raise ValueError("external_id is required")
    payload = (
        f"{IDENTITY_VERSION}\0{source_id}\0{normalized_external_id}".encode("utf-8")
    )
    return hashlib.sha256(payload).hexdigest()


def raw_document_id(source_id: ID, external_id: str) -> ID:
    """Derive the stable application ID that persistence stores and validates.

    Ingestion owns this ID; persistence must neither generate a replacement
    nor substitute a database-specific identifier.
    """
    return f"raw_{collection_identity(source_id, external_id)}"


@dataclass(frozen=True, slots=True)
class DeduplicationResult:
    """Pure batch decision; callers decide how identities are persisted."""

    accepted: tuple[RawDocument, ...]
    duplicate_ids: tuple[ID, ...]


def deduplicate_documents(
    documents: Iterable[RawDocument],
    *,
    known_document_ids: frozenset[ID] = frozenset(),
) -> DeduplicationResult:
    """Remove repeated document identities without discarding provenance records.

    The function has no storage dependency. Phase 7.2 repositories will supply
    known identities and enforce the same identity with a unique constraint.
    """
    seen = set(known_document_ids)
    accepted: list[RawDocument] = []
    duplicate_ids: list[ID] = []
    for document in documents:
        if document.id in seen:
            duplicate_ids.append(document.id)
            continue
        seen.add(document.id)
        accepted.append(document)
    return DeduplicationResult(
        accepted=tuple(accepted),
        duplicate_ids=tuple(duplicate_ids),
    )
