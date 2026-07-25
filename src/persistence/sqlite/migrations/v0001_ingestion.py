"""Initial durable-ingestion SQLite schema."""

from __future__ import annotations

VERSION = 1
NAME = "initial_ingestion"

STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE schema_migrations (
        version INTEGER NOT NULL PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
        checksum TEXT NOT NULL,
        applied_at TEXT NOT NULL,
        tool_version TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE documents (
        id TEXT NOT NULL PRIMARY KEY,
        source_id TEXT NOT NULL,
        external_id TEXT NOT NULL,
        canonical_uri TEXT NOT NULL,
        published_at TEXT NOT NULL,
        retrieved_at TEXT NOT NULL,
        media_type TEXT NOT NULL,
        title TEXT,
        content TEXT,
        raw_payload_ref TEXT,
        content_hash TEXT NOT NULL,
        connector_name TEXT NOT NULL,
        connector_version TEXT NOT NULL,
        provider_metadata_json TEXT NOT NULL DEFAULT '[]',
        schema_version TEXT NOT NULL,
        created_at TEXT NOT NULL,
        CONSTRAINT uq_documents_collection_identity
            UNIQUE (source_id, external_id),
        CONSTRAINT ck_documents_payload
            CHECK (content IS NOT NULL OR raw_payload_ref IS NOT NULL)
    )
    """,
    """
    CREATE INDEX ix_documents_source_published
    ON documents (source_id, published_at)
    """,
    """
    CREATE INDEX ix_documents_content_hash
    ON documents (content_hash)
    """,
    """
    CREATE INDEX ix_documents_connector
    ON documents (connector_name, connector_version)
    """,
    """
    CREATE INDEX ix_documents_retrieved_at
    ON documents (retrieved_at)
    """,
    """
    CREATE TABLE deduplication_identities (
        identity_kind TEXT NOT NULL,
        identity_key TEXT NOT NULL,
        document_id TEXT NOT NULL,
        identity_version TEXT NOT NULL,
        created_at TEXT NOT NULL,
        CONSTRAINT pk_deduplication_identities
            PRIMARY KEY (identity_kind, identity_key, document_id),
        CONSTRAINT ck_deduplication_identity_kind
            CHECK (identity_kind IN ('collection', 'content')),
        CONSTRAINT fk_deduplication_document
            FOREIGN KEY (document_id) REFERENCES documents (id)
            ON UPDATE RESTRICT ON DELETE RESTRICT
    )
    """,
    """
    CREATE UNIQUE INDEX uq_deduplication_collection_identity
    ON deduplication_identities (identity_kind, identity_key)
    WHERE identity_kind = 'collection'
    """,
    """
    CREATE INDEX ix_deduplication_document
    ON deduplication_identities (document_id)
    """,
    """
    CREATE INDEX ix_deduplication_resolve
    ON deduplication_identities (
        identity_kind,
        identity_key,
        identity_version,
        document_id
    )
    """,
    """
    CREATE TABLE collection_checkpoints (
        source_id TEXT NOT NULL PRIMARY KEY,
        cursor TEXT,
        watermark TEXT,
        last_success_at TEXT,
        connector_name TEXT NOT NULL,
        connector_version TEXT NOT NULL,
        revision INTEGER NOT NULL,
        schema_version TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        CONSTRAINT ck_collection_checkpoint_revision
            CHECK (revision >= 0)
    )
    """,
    """
    CREATE INDEX ix_collection_checkpoints_last_success
    ON collection_checkpoints (last_success_at)
    """,
    """
    CREATE INDEX ix_collection_checkpoints_connector
    ON collection_checkpoints (connector_name, connector_version)
    """,
    """
    CREATE TABLE work_items (
        id TEXT NOT NULL PRIMARY KEY,
        kind TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        payload_schema_version TEXT NOT NULL,
        idempotency_key TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        priority INTEGER NOT NULL DEFAULT 50,
        available_at TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        revision INTEGER NOT NULL DEFAULT 0,
        CONSTRAINT uq_work_items_kind_idempotency
            UNIQUE (kind, idempotency_key),
        CONSTRAINT ck_work_items_kind
            CHECK (kind IN ('collection', 'document_processing', 'research')),
        CONSTRAINT ck_work_items_pending_only
            CHECK (status = 'pending'),
        CONSTRAINT ck_work_items_initial_revision
            CHECK (revision = 0)
    )
    """,
    """
    CREATE INDEX ix_work_items_pending_order
    ON work_items (status, available_at, priority, created_at)
    """,
    """
    CREATE INDEX ix_work_items_kind_status
    ON work_items (kind, status)
    """,
    """
    CREATE INDEX ix_work_items_updated_at
    ON work_items (updated_at)
    """,
)
