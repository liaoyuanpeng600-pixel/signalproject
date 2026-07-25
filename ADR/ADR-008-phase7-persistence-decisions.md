# ADR-008: Phase 7 Persistence Decisions

> **Status:** Accepted
> **Date:** 2026-07-25
> **Accepted Date:** 2026-07-25
> **Acceptance Note:** The decisions were reviewed and accepted as the
> persistence foundation for Phase 7 implementation.
> **Supersedes:** None
> **Superseded by:** None
> **Related RFC:** RFC-001

## Context

Phase 7.1 established provider-neutral, persistence-independent contracts for:

- `RawDocument`;
- `CollectionBatch`;
- `IngestionCheckpoint`;
- deterministic collection and content identities;
- `CollectionWorkItem`;
- `DocumentProcessingWorkItem`;
- `ResearchWorkItem`;
- `CollectionRunner`.

Those contracts are validated without imports from persistence, runtime,
reports, research, Signal, or Evidence. Phase 7.2 must make ingestion state
durable without redesigning those contracts or placing provider/database types
inside them.

The persistence layer must support:

- restart-safe collected-document identity and provenance;
- race-safe deduplication;
- optimistic checkpoint advancement;
- idempotent typed work creation;
- future work claiming and lease recovery;
- explicit schema migrations;
- a later PostgreSQL path.

This ADR is an architecture decision only. It introduces no SQLite code,
repository implementation, migration, runtime queue, worker, lease, or
scheduler.

## Decision Status and Scope

The decisions below are **accepted** as the Phase 7 persistence foundation.

In scope:

- candidate SQLite tables, constraints, and indexes;
- atomic operation boundaries;
- future concurrency requirements;
- migration ownership and compatibility;
- Phase 7.1 contract mapping.

Out of scope:

- SQL or Python implementation;
- repository classes;
- migration files;
- worker processes;
- queue polling;
- lease algorithms in executable code;
- changes to `Store`;
- changes to core, Evidence, Signal, Research, or Report.

## Decisions

### 1. System of record

SQLite is the Phase 7 MVP durable system of record for ingestion metadata,
normalized document content or payload references, checkpoints, deduplication
identities, work state, and migration history.

Large raw payloads remain outside SQLite. `raw_payload_ref` and `content_hash`
bind the database record to immutable external payload storage.

SQLite configuration proposed for implementation review:

- foreign keys enabled for every connection;
- WAL mode evaluated and enabled unless filesystem constraints reject it;
- finite busy timeout;
- explicit transaction control;
- UTC ISO8601 timestamps stored in canonical text form;
- no correctness dependency on SQLite JSON query functions.

### 2. Repository boundary

Phase 7.2 introduces narrow persistence ports driven by the transactions in
this ADR. It does not add ingestion objects or work state to the existing broad
`Store` interface.

The existing Store remains a compatibility facade for current core, research,
runtime, and tests. `InMemoryStore` remains available.

Candidate ports, to be designed in implementation review rather than approved
as CRUD interfaces here:

- document insertion and identity lookup;
- checkpoint read and compare-and-set;
- atomic collection commit;
- work enqueue-if-absent and state lookup;
- schema migration inspection.

Repository implementations return Phase 7.1 application models or explicit
result DTOs. They do not expose SQLite rows or connections.

### 3. Phase 7.1 contracts are consumed unchanged

| Phase 7.1 contract | Persistence use |
|---|---|
| `RawDocument.id` | `documents.id` primary key |
| `source_id + external_id` | Collection identity unique constraint |
| `RawDocument.content_hash` | Integrity/deduplication index; not globally unique |
| `RawDocument.schema_version` | Per-record application schema version |
| `IngestionCheckpoint.revision` | Compare-and-set version |
| `IngestionCheckpoint.cursor` | Opaque connector cursor; database does not parse |
| `IngestionCheckpoint.connector_version` | Checkpoint connector-version compatibility |
| `CollectionWorkItem.connector_name` | Persisted checkpoint connector name |
| `CollectionWorkItem.connector_version` | Validated against the checkpoint version |
| WorkItem `id` | `work_items.id` primary key |
| WorkItem `idempotency_key` | Race-safe enqueue uniqueness with work kind |
| WorkItem `schema_version` | Typed payload decoder selection |
| `CollectionBatch.is_partial` | Default prohibition on checkpoint advancement |
| `DeduplicationResult` | Application decision input; database constraints remain authoritative |

No persistence field changes the meaning of these contracts.

`collection_checkpoints.connector_name` is persistence metadata composed from
the connector-bound `CollectionWorkItem`. `connector_version` comes from
`IngestionCheckpoint` and must equal the version on the CollectionWorkItem.
The repository validates both during collection persistence. This does not
modify the Phase 7.1 `IngestionCheckpoint` contract.

## Proposed SQLite Architecture

### Table 1: `documents`

#### Purpose

Store the durable provider-neutral RawDocument envelope and its provenance.
This is pre-Evidence ingestion state, not a domain Evidence table.

#### Candidate columns

```text
id                      TEXT NOT NULL
source_id               TEXT NOT NULL
external_id             TEXT NOT NULL
canonical_uri           TEXT NOT NULL
published_at            TEXT NOT NULL
retrieved_at            TEXT NOT NULL
media_type              TEXT NOT NULL
title                   TEXT NULL
normalized_content      TEXT NULL
raw_payload_ref         TEXT NULL
content_hash            TEXT NOT NULL
connector_name          TEXT NOT NULL
connector_version       TEXT NOT NULL
provider_metadata_json  TEXT NOT NULL DEFAULT '{}'
schema_version          TEXT NOT NULL
created_at              TEXT NOT NULL
```

The table enforces that at least one of `normalized_content` or
`raw_payload_ref` is present. Provider metadata is serialized as bounded JSON
but is not used for correctness queries.

#### Primary key

```text
PRIMARY KEY (id)
```

`id` consumes the deterministic `RawDocument.id`.

#### Unique constraints

```text
UNIQUE (source_id, external_id)
```

This is the authoritative collection-idempotency constraint.

`content_hash` is deliberately not globally unique. Identical content may be
observed through different Sources, external records, or retrieval contexts;
their provenance must be retained.

#### Indexes

```text
INDEX (source_id, published_at)
INDEX (content_hash)
INDEX (connector_name, connector_version)
INDEX (retrieved_at)
```

No index is proposed on provider metadata.

#### Lifecycle

Append-only for document identity and normalized content. A repeated
`source_id + external_id` resolves to the existing record after equivalence
checks. Content changes for the same provider identity must not silently
overwrite the row; they are treated as a provider revision conflict until a
separate revision policy is approved.

No hard-delete API is part of Phase 7.2. Retention and Evidence revision remain
separate governance concerns.

### Table 2: `collection_checkpoints`

#### Purpose

Store one committed progress position for a Source and connector binding.

#### Candidate columns

```text
source_id          TEXT NOT NULL
cursor             TEXT NULL
watermark          TEXT NULL
last_success_at    TEXT NULL
connector_name     TEXT NOT NULL
connector_version  TEXT NOT NULL
revision           INTEGER NOT NULL
schema_version     TEXT NOT NULL
updated_at         TEXT NOT NULL
```

`cursor` remains opaque. SQLite and repositories must not interpret or rewrite
connector cursor payloads.

#### Primary key

```text
PRIMARY KEY (source_id)
```

The MVP allows one active connector binding per Source. Changing connector
name/version requires an explicit checkpoint reset or migration.

#### Unique constraints

The primary key is sufficient. `revision >= 0` is enforced with a check
constraint.

#### Indexes

```text
INDEX (last_success_at)
INDEX (connector_name, connector_version)
```

#### Lifecycle

Created at revision 0. Each successful compare-and-set update increments the
revision by one. Checkpoints are updated only inside an accepted collection
transaction. A stale expected revision changes zero rows and returns a
checkpoint conflict.

For initial creation, `expected_revision = None` means the checkpoint must not
exist. If two transactions concurrently attempt initial creation:

1. The first insert succeeds.
2. The second uniqueness conflict maps to `CheckpointConflictError`.
3. The second transaction rolls back in full.
4. Its caller reloads the committed checkpoint before retrying.

This is an optimistic-concurrency outcome, not a generic integrity failure.

A partial batch does not advance the checkpoint unless a future connector
contract explicitly marks a subset cursor as safely commit-complete. Phase
7.1 currently supplies no such marker, so `is_partial=True` means no
advancement.

### Table 3: `deduplication_identities`

#### Purpose

Provide explicit, queryable identity claims beyond the direct document unique
constraint and support future identity kinds without changing `documents`.

#### Candidate columns

```text
identity_kind     TEXT NOT NULL
identity_key      TEXT NOT NULL
document_id       TEXT NOT NULL
identity_version  TEXT NOT NULL
created_at        TEXT NOT NULL
```

Initial identity kinds:

```text
collection
content
```

`collection` represents the versioned `source_id + external_id` identity.
`content` records the normalized content hash. A content identity may map to
multiple documents, so it is not unique by itself.

#### Primary key

```text
PRIMARY KEY (identity_kind, identity_key, document_id)
```

#### Unique constraints

For collection identity:

```text
UNIQUE (identity_kind, identity_key)
WHERE identity_kind = 'collection'
```

No equivalent uniqueness is applied to `content`.

#### Foreign keys

```text
document_id REFERENCES documents(id)
```

#### Indexes

```text
INDEX (document_id)
INDEX (identity_kind, identity_key)
```

#### Lifecycle

Append-only. An identity is never reassigned to another document. A conflicting
collection identity with non-equivalent content is surfaced for investigation,
not overwritten.

### Table 4: `work_items`

#### Purpose

Persist typed application work and its future execution state without reusing
or modifying `runtime.WorkItem` or `runtime.WorkQueue`.

The initial Phase 7.2 scope stores **durable pending typed work only**. It does
not implement execution, claiming, retries, leases, or dead-letter handling.

#### Candidate columns

```text
id                    TEXT NOT NULL
kind                  TEXT NOT NULL
payload_json          TEXT NOT NULL
payload_schema_version TEXT NOT NULL
idempotency_key       TEXT NOT NULL
status                TEXT NOT NULL
priority              INTEGER NOT NULL DEFAULT 50
available_at          TEXT NOT NULL
created_at            TEXT NOT NULL
updated_at            TEXT NOT NULL
revision              INTEGER NOT NULL DEFAULT 0
```

Initial `kind` values consume Phase 7.1 contracts:

```text
collection
document_processing
research
```

Payload JSON is typed by `kind + payload_schema_version`; it is not an
unrestricted application dictionary. Phase 7.2 must define exact codecs and
round-trip tests for the existing dataclasses.

The initial allowed status is:

```text
pending
```

The following fields and transitions are explicitly deferred:

```text
lease_owner
lease_expires_at
attempt_count
retry transitions
dead-letter transitions
last_error_category
last_error_message
```

They require a separate approved worker/lease architecture decision and a
subsequent migration. Initial Phase 7.2 persistence must not write or infer
them.

#### Primary key

```text
PRIMARY KEY (id)
```

#### Unique constraints

```text
UNIQUE (kind, idempotency_key)
```

On conflict, the repository verifies that the existing kind, payload schema,
and canonical payload are equivalent. A conflicting key with different
payload is an integrity error, not an idempotent success.

#### Indexes

```text
INDEX (status, available_at, priority, created_at)
INDEX (kind, status)
INDEX (updated_at)
```

#### Lifecycle

The following transition graph is illustrative future scope and is not
authorized by this ADR:

```text
pending  → running | cancelled
running  → completed | retrying | dead_letter
retrying → running | dead_letter | cancelled
```

`completed`, `dead_letter`, and `cancelled` are terminal for the original work
item. Replay creates a new work item with a new explicit replay identity; it
does not reset terminal history.

Initial Phase 7.2 lifecycle is insert-once in `pending` status and read-only
inspection. No transition out of `pending` is authorized. Claiming, completion,
cancellation, retry, and dead-letter behavior require a separate approved
worker/lease architecture decision and subsequent migration.

### Table 5: `schema_migrations`

#### Purpose

Record the ordered database schema history applied to one SQLite database.

#### Candidate columns

```text
version       INTEGER NOT NULL
name          TEXT NOT NULL
checksum      TEXT NOT NULL
applied_at    TEXT NOT NULL
tool_version  TEXT NOT NULL
```

#### Primary key

```text
PRIMARY KEY (version)
```

#### Unique constraints

```text
UNIQUE (name)
```

An already-applied migration with a different checksum is a startup error.

#### Indexes

The primary key and unique name index are sufficient.

#### Lifecycle

Append-only. Applied rows are never edited or removed. Rollback during
development restores a database backup or uses an explicitly reviewed
down-migration; migration history is not rewritten.

SQLite `PRAGMA user_version` may mirror the latest version for diagnostics but
is not the authoritative migration history.

## Transaction Model

### 1. Connector execution boundary

External I/O occurs outside a database write transaction:

```text
read checkpoint
→ Connector.collect()
→ validate CollectionBatch
→ derive deterministic identities and work
→ begin collection transaction
```

This avoids holding SQLite write locks during network or file I/O.

Before commit, the transaction rechecks the checkpoint revision used to
prepare the collection. A stale batch is reconciled through idempotency or
recollected; it must not overwrite a newer checkpoint.

### 2. Atomic collection-ingestion transaction

One complete, non-partial CollectionBatch is committed atomically:

```text
BEGIN
  verify checkpoint expected revision
  for each RawDocument:
    insert document if collection identity is absent
    otherwise load and verify equivalent existing document
    insert collection/content identity rows if absent
    enqueue DocumentProcessingWorkItem if document was newly accepted
  advance checkpoint with compare-and-set
COMMIT
```

The operation returns explicit counts and IDs:

```text
documents_inserted
documents_existing
document_work_created
document_work_existing
checkpoint_revision
```

No caller infers success from a swallowed uniqueness exception.

### 3. Document insertion behavior

Candidate outcomes:

1. New primary key and new collection identity: insert.
2. Existing equivalent document: idempotent success, no duplicate work.
3. Different primary key but existing collection identity with equivalent
   canonical fields: return the existing document identity.
4. Same identity with different content/provenance fields: integrity conflict;
   roll back the transaction.
5. Existing content hash under another collection identity: retain the new
   document provenance and relate the content identity to both documents.

Equivalence fields must include at least:

```text
source_id
external_id
content_hash
connector_name
connector_version
schema_version
```

### 4. Checkpoint advancement

Create:

```text
INSERT checkpoint at revision 0
```

Creation is conditional on absence: `expected_revision = None` means no
checkpoint may already exist. A uniqueness conflict during initial creation
maps to `CheckpointConflictError`, rolls back the complete collection
transaction, and requires the caller to reload the committed checkpoint before
retry.

Update:

```text
UPDATE collection_checkpoints
SET ..., revision = revision + 1
WHERE source_id = ? AND revision = expected_revision
```

An update count of zero is `CheckpointConflictError`.

Checkpoint advancement commits in the same transaction as document identities
and document work. It never commits first.

Rules:

- complete empty batch: may update `last_success_at` and revision;
- complete non-empty batch: commits documents, work, and next cursor together;
- partial batch: default rollback/no checkpoint advancement;
- connector name/version mismatch: explicit migration/reset required;
- invalid cursor: collection fails before transaction.

### 5. Work creation

Work insertion uses the Phase 7.1 deterministic ID and:

```text
UNIQUE (kind, idempotency_key)
```

The repository performs insert-if-absent inside the owning business
transaction. On conflict it reads and verifies the existing typed payload.

Document work is created only for newly accepted document identity. Research
work remains created only after the existing Evidence/Signal eligibility
boundary supplies Signal IDs; persistence must not derive it from RawDocument.

### 6. Failure recovery

| Failure point | Durable outcome | Recovery |
|---|---|---|
| Connector fails before transaction | No database change | Retry collection according to caller policy |
| Validation fails | No database change | Correct input/connector; do not advance checkpoint |
| Document insert fails | Transaction rolls back | Re-run same deterministic batch |
| Work insert fails | Documents and checkpoint roll back | Re-run; uniqueness makes replay safe |
| Checkpoint CAS conflicts | Entire transaction rolls back | Reload checkpoint and recollect/reconcile |
| Process exits before COMMIT | SQLite rolls back transaction | Same collection work may run again |
| Process exits after COMMIT | Full batch is durable | Repeated work resolves idempotently |

The transaction boundary ensures there is no committed checkpoint whose
documents or downstream work are missing.

## Concurrency Model

### MVP concurrency

The initial SQLite deployment should use:

- one write-intensive ingestion worker;
- any number of read-only consumers consistent with SQLite locking limits;
- short write transactions;
- no database connection shared concurrently across threads;
- bounded busy timeout and explicit lock-error classification.

Correctness must not depend solely on the single-worker deployment. Unique
constraints and checkpoint compare-and-set remain authoritative.

### Future multiple-worker requirements

Multiple workers require all of:

- atomic claim of one eligible work row;
- conditional state/revision update;
- stable worker identity;
- finite lease expiry;
- owner-checked completion and failure;
- attempt increments on successful claim;
- reclaim of expired work;
- structured transition audit;
- no reliance on `SELECT` followed by an unconditional `UPDATE`.

These requirements are not represented by executable transitions or initial
lease/retry/dead-letter columns. They require a separate worker/lease
architecture decision followed by a versioned database migration.

### Proposed future claiming semantics

Architecture requirement, not implementation:

```text
BEGIN IMMEDIATE
  select highest-priority due work
  conditional update:
    pending/retrying → running
    set lease_owner
    set lease_expires_at
    increment attempt_count and revision
COMMIT
```

If the conditional update affects zero rows, the worker did not claim the
item. It retries selection after a bounded delay.

SQLite lacks PostgreSQL `SKIP LOCKED`; claiming must remain a short serialized
write transaction. PostgreSQL migration becomes a priority if measured claim
contention or write latency breaches the accepted operational threshold.

### Future lease requirements

- Lease duration is bounded and configurable by work kind.
- Only the current owner and unexpired lease may complete work.
- Heartbeat/renewal, if later needed, is owner- and revision-conditional.
- Expired `running` work is reclaimable.
- Reclaim records the prior owner and increments the attempt count.
- Exceeding the attempt budget transitions to `dead_letter`.
- Wall-clock comparison uses UTC; long operations must not assume a lease is
  still valid at commit.

Lease and retry policy require a separate implementation review before workers
are enabled.

## Migration Strategy

### Schema version layers

Three independent versions are retained:

1. **Database migration version** in `schema_migrations`.
2. **Application payload schema version** already present on RawDocument,
   checkpoints, and WorkItems.
3. **Project SPEC_VERSION**, governed separately by `SPEC_VERSION.md`.

Database migration version does not replace application schema versions.

### Migration ownership

The persistence package owns:

- ordered migration artifacts;
- migration checksums;
- transaction wrapping;
- compatibility probes;
- repository conformance tests;
- database backup/restore instructions.

Ingestion owns its serializers and payload schema versions. Core and research
do not import migration code.

### Migration rules

- Migrations are monotonic and applied in numeric order.
- Each migration runs in a transaction where SQLite permits it.
- The application refuses to open a database newer than it supports.
- The application migrates an older supported database before normal writes.
- Applied migration checksums are verified.
- Destructive migrations require an explicit backup and separate review.
- Schema inference from dataclass fields is prohibited.
- Tests cover empty database creation and upgrade from every supported prior
  migration baseline.

### Backward compatibility

- Phase 7.1 in-memory contracts remain available.
- `InMemoryCursorStore` remains valid for unit tests.
- Existing `Store` and `InMemoryStore` are not removed or expanded.
- Repository decoders read supported older payload schema versions through
  explicit adapters.
- Writers emit only the current payload schema version.
- A payload major-version change requires a migration or compatibility adapter
  before deployment.
- No ORM or SQLite row type crosses the persistence boundary.

### PostgreSQL migration path

The logical model avoids SQLite-only correctness:

- stable text IDs;
- explicit unique constraints;
- explicit revisions;
- normalized work-state columns;
- application-level payload codecs;
- repository conformance tests.

SQLite transaction/claim syntax is infrastructure-specific and may be replaced
without changing ingestion contracts.

## Alternatives Considered

### Extend the existing Store with documents, checkpoints, and work

Rejected. Store is already a broad compatibility abstraction for current
domain objects. Adding operational ingestion and queue concerns would expand
it into an unbounded service locator and force unrelated backends to implement
Phase 7.2 behavior.

### One table per typed WorkItem

Rejected for the MVP. The three work kinds share execution identity and state.
A common envelope with typed, versioned payloads supports uniform idempotency
and future claiming without pretending payloads are untyped.

### Store all RawDocument fields as one JSON blob

Rejected. Identity, provenance, time-window queries, constraints, and content
hashes require explicit columns. Provider metadata may remain bounded JSON
because it is not used for correctness.

### Make content hash globally unique

Rejected. Equal content from different Sources or external records has
different provenance and must remain separately observable.

### Advance checkpoint in a separate transaction

Rejected. It can commit progress while documents or work are missing after a
failure.

### Use SQLite `INSERT OR REPLACE`

Rejected. Replace semantics can silently delete/reinsert rows, bypass
equivalence checks, break foreign keys, and erase history.

### Persist only WorkItems and reconstruct documents from payloads

Rejected. RawDocument is authoritative ingestion provenance and must survive
work completion, retry, and dead-letter transitions independently.

### Event Sourcing

Rejected for Phase 7.2. Full state reconstruction from events is unnecessary.
Explicit tables, append-oriented identities, migration history, and future
transition audit provide the required durability with lower complexity.

### PostgreSQL immediately

Not selected for the MVP per ADR-007. Repository boundaries and conformance
tests preserve a migration path if SQLite concurrency becomes insufficient.

### Filesystem-only persistence

Rejected. Files are suitable for large immutable raw payloads but do not
provide transactional checkpoint movement, uniqueness, work state, or
concurrent compare-and-set.

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Checkpoint advances before durable records | One atomic collection transaction |
| Duplicate documents under retries | Deterministic IDs plus `source_id, external_id` uniqueness |
| Same idempotency key carries different work | Verify canonical typed payload on conflict |
| Content dedupe erases provenance | Content hash is indexed but not globally unique |
| Provider revision conflicts with append-only document | Reject conflict; define revision behavior separately |
| SQLite write contention | One initial writer, short transactions, WAL evaluation, metrics and PostgreSQL exit criteria |
| Stale collector overwrites progress | Checkpoint revision compare-and-set |
| Partial batch loses data | No checkpoint advancement under current contract |
| JSON payload becomes untyped | Require kind + schema version codec and round-trip tests |
| Migration drift | Ordered checksummed migration ledger |
| Database newer than application | Fail closed before writes |
| Lease design leaks into Phase 7.2 foundation | Exclude lease/retry/dead-letter columns and transitions; require separate decision and migration |
| Broad exception swallowing | Typed repository errors; uniqueness handled only after equivalence verification |
| Large blobs make SQLite unstable | Store immutable external reference and integrity hash |
| Store facade expands indefinitely | Keep operational repositories separate |

## Future Constraints

Any Phase 7.2 implementation must:

- consume Phase 7.1 IDs, cursors, schema versions, and typed work;
- preserve Evidence-first research lineage;
- keep connector calls outside write transactions;
- atomically commit documents, identities, document work, and checkpoints;
- use database uniqueness as the final race-safe idempotency guarantee;
- use checkpoint revision compare-and-set;
- never use `INSERT OR REPLACE` for authoritative records;
- never treat all integrity errors as duplicate success;
- keep provider metadata out of correctness queries;
- keep raw large payloads outside core database fields;
- avoid modifying runtime.WorkItem, runtime.WorkQueue, Store, or core;
- pass repository conformance, rollback, restart, and duplicate-input tests;
- obtain separate approval before enabling multi-worker claim/lease behavior.

## Consequences

### Positive

- Phase 7.1 remains stable and persistence-independent.
- Restart safety and idempotency have explicit database guarantees.
- Checkpoint/data/work consistency has one reviewable transaction boundary.
- SQLite implementation remains replaceable through narrow ports.
- Future worker concurrency has defined prerequisites without being prematurely
  implemented.

### Negative

- Collection ingestion requires a multi-table transaction.
- Typed payload codecs and equivalence checks add implementation work.
- Provider revisions remain a deliberate conflict until a revision model is
  approved.
- SQLite serializes write-heavy operations and may require later migration.
- Migration history and compatibility tests become ongoing maintenance.

## Acceptance Gates for Implementation

The acceptance review approved the following gates for Phase 7.2
implementation planning:

1. The five-table logical model.
2. The atomic collection transaction.
3. The partial-batch checkpoint rule.
4. The document equivalence fields.
5. The typed WorkItem payload codec approach.
6. The separation between Store and Phase 7 repositories.
7. The migration ledger and checksum policy.
8. Lease, retry, and dead-letter fields are excluded initially and require a
   later approved worker/lease migration.

With those gates accepted:

```text
ADR-008: Accepted
SQLite implementation: Not started
Phase 7.1 contracts: Unchanged
```

## References

- [RFC-001: Durable Ingestion and Research Triggering](../RFC/RFC-001-durable-ingestion-research-triggering.md)
- [ADR-007: Phase 7 Foundation Decisions](ADR-007-phase7-foundation-decisions.md)
- [Phase 7.1 ingestion models](../src/ingestion/models.py)
- [Phase 7.1 work contracts](../src/ingestion/work.py)
- [Phase 7.1 cursor contract](../src/ingestion/cursor.py)
- [Phase 7.1 collection orchestration](../src/ingestion/service.py)
- [Specification Versioning](../SPEC_VERSION.md)
- [Schema Evolution](../SCHEMA_EVOLUTION.md)
