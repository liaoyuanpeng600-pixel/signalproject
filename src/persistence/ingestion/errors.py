"""Persistence-neutral failures for durable ingestion contracts."""

from __future__ import annotations


class PersistenceError(Exception):
    """Base class for persistence contract failures."""


class PersistenceOperationalError(PersistenceError):
    """A storage operation failed for a reason other than a contract conflict."""


class DocumentConflictError(PersistenceError):
    """An authoritative document identity exists with non-equivalent content."""


class IdentityConflictError(PersistenceError):
    """A collection identity was claimed by a different document."""


class CheckpointConflictError(PersistenceError):
    """Checkpoint creation, revision CAS, or connector binding conflicted."""


class WorkItemConflictError(PersistenceError):
    """A work identity exists with a non-equivalent canonical payload."""


class PayloadCompatibilityError(PersistenceError):
    """A work kind, payload schema, or canonical payload is unsupported."""


class MigrationCompatibilityError(PersistenceError):
    """Database migration history is incompatible with this application."""
