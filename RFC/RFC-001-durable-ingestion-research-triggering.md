# RFC-001: Phase 7 — Durable Ingestion and Research Triggering

> **Status:** accepted
> **Target:** post-v0.1.0 / Phase 7
> **Date:** 2026-07-25
> **Last updated:** 2026-07-25
> **Author:** Signal Project Principal Engineer (RFC Author)
> **Reviewers:** TBD
> **Supersedes:** None
> **Superseded by:** None
> **Related ADRs:** ADR-007

---

## 1. Status

This RFC has been accepted as the Phase 7 architecture decision freeze. Its
approved decisions authorize Phase 7.1 planning and implementation to begin,
but do not themselves implement or migrate any runtime, schema, or code.

The target is Phase 7, after the released v0.1.0 baseline. No named reviewer is
invented by this record. The accepted foundation decisions are recorded in
[ADR-007](../ADR/ADR-007-phase7-foundation-decisions.md) following the
lifecycle in [RFC/README.md](README.md) and
[GOVERNANCE.md](../GOVERNANCE.md).

---

## 2. Executive Summary

v0.1.0 already defines `Source`, `Evidence`, `Signal`, `Research`, and `Thesis`
as first-class domain objects and implements a six-stage workflow, in-memory
runtime, research services, and deterministic reports. Phase 7 therefore does
not rebuild the Signal model. It adds the missing external-input boundary,
durable state, idempotent incremental processing, deterministic research
triggering, and restart recovery.

This RFC proposes a modular monolith with SQLite as the MVP system of record,
typed database-backed work items, two connectors, and preservation of the
existing Evidence-first research chain. A general event bus, knowledge graph,
Event Sourcing, and agent-controlled runtime are excluded.

The objective is:

> Enable Signal Project to continuously collect external information, preserve
> provenance, deduplicate and checkpoint processing, trigger research
> deterministically, and resume safely after interruption.

---

## 3. Context and Current State

### 3.1 Verified repository state

The Phase 7 architecture review used as an input to this RFC was provided in
the design-review conversation. No Phase 7 review artifact exists in the
repository, so this RFC does not invent a repository path for it.

The repository also has no `docs/specifications/` directory. The authoritative
documents actually present are the frozen specifications directly under
`docs/`, the root specification set, and the governance material in `RFC/` and
`ADR/`.

Code and tests establish the following current state:

- `Source`, `Evidence`, `Signal`, `Research`, and `Thesis` are first-class core
  objects.
- The canonical workflow has six stages:
  Source Observation, Evidence Production, Signal Extraction, Research
  Synthesis, Thesis Update, and Knowledge Update.
- Stage implementation ports already exist as `Protocol` types in
  `src/workflow/stages.py`.
- `Store` provides object-specific `put`, `get`, and unfiltered `list`
  operations, append-only overrides, and whole-store `snapshot`/`restore`.
- `InMemoryStore` is the only Store backend. It is not thread-safe.
- Evidence rejects overwrite by ID, but its present correction helper does not
  persist an explicit link to the corrected Evidence or the supplied reason.
- The runtime queue, scheduler state, audit logger, retry state, and dead-letter
  queue are in-process structures. Binding `WorkQueue` to a Store is currently
  reserved and does not make the queue durable.
- The current `WorkItem` represents a whole pipeline cycle and has no typed
  payload, lease, attempt counter, availability time, or idempotency key.
- `PipelineContext` carries one cycle's inputs and outputs in mutable in-memory
  lists.
- `Pipeline.run()` catches stage exceptions and continues; the tests explicitly
  preserve this behavior.
- `RuntimeCycle` catches any exception from Evidence persistence and suppresses
  it. This is acceptable only as a known v0.1.0 limitation, not as a production
  persistence policy.
- Reports accept domain objects and runtime result DTOs. They do not import
  persistence or ORM types.
- The public Python package namespace is currently `src`.

The current canonical chain is:

```text
Source
  → CandidateObservation
  → Evidence
  → Signal
  → Research
  → Thesis
  → Knowledge
  → Report
```

### 3.2 Current Architecture Map

| Module | Current responsibility | Current limitation relevant to Phase 7 |
|---|---|---|
| `src/core` | Domain objects, identity, lifecycle, invariants | No raw-document identity, ingestion checkpoint, or explicit Evidence revision relation |
| `src/workflow` | Six-stage orchestration, gates, failure routing, implementation ports | Whole-cycle in-memory context; ports have no production connector implementations |
| `src/persistence` | Broad Store abstraction, in-memory backend, lifecycle helpers, snapshots, overrides | No durable backend, transactions, pagination, filtered queries, optimistic concurrency, or durable work state |
| `src/runtime` | Scheduling, queueing, execution, validation, retry, audit, dead letter | Queue, audit, retry and scheduler state do not survive restart; work is cycle-grained |
| `src/research` | Promotion, synthesis, curation, themes, conflicts, calibration | Consumes existing Signals; no durable or auditable research-trigger decision boundary |
| `src/reports` | Deterministic report inputs, builders, renderers, JSON export | No query projection for time-window, entity/topic, or full lineage retrieval |
| `RFC/` and `ADR/` | Proposal and accepted-decision governance | No Phase 7 RFC or accepted Phase 7 ADR exists |

### 3.3 Current gap

The domain model exists, but external data entry, incremental processing,
durable recovery, and continuous execution do not yet form a closed loop.

Phase 7 is therefore defined as:

```text
Phase 7 = Durable Ingestion and Research Triggering
```

It is not a redesign of the canonical Signal domain.

---

## 4. Problem Statement

Phase 7 must solve the following engineering problems.

1. **External source integration.** There is a `SourceObserver` port but no
   production boundary that consistently handles provider communication,
   cursors, batches, and failures. Phase 7 must collect from two bounded source
   types through explicit connector implementations.

2. **Provider isolation.** Without a connector boundary, provider SDK types,
   HTTP responses, authentication, and error conventions could leak into
   workflow or research code. Phase 7 must terminate provider-specific
   semantics at the connector.

3. **Raw input normalization.** `CandidateObservation` is deliberately small
   and lacks external identity, media type, content hash, connector version,
   and raw-payload reference. Phase 7 needs an ingestion envelope before
   Evidence production.

4. **Provenance preservation.** Existing Evidence records sources and content
   locators, but continuous ingestion also needs document identity, collection
   run, connector version, extraction version, and revision lineage.

5. **Incremental collection.** The current runtime loads all active Sources
   per cycle and has no durable per-Source cursor or watermark. Phase 7 must
   resume collection from a committed checkpoint.

6. **Deduplication and idempotency.** Retries and overlapping provider pages
   must not create duplicate RawDocuments, Evidence, Signals, research work,
   or report runs.

7. **Durable checkpoints.** A process crash must not advance a cursor past
   records that were not committed. Checkpoints must be transactional with
   accepted collection results.

8. **Durable work queue.** Current WorkQueue and DeadLetterQueue are in memory.
   Phase 7 needs typed, leased, retryable work items stored in the relational
   database.

9. **Research triggering.** Verified or active Signals need a deterministic,
   versioned, auditable decision that can ignore, hold, merge, or create
   research work. A draft Signal must not update a Thesis.

10. **Restart and failure recovery.** Pending work, expired leases, retry
    attempts, dead letters, and ingestion progress must survive restart.

11. **Operational observability.** Operators need structured, queryable state
    for connector health, conversion rates, queue state, and failures without
    requiring a monitoring platform in the MVP.

---

## 5. Goals

Phase 7 proposes to:

- support exactly two MVP connectors;
- prevent provider APIs and SDK types from entering `core`, `research`, or
  report construction;
- preserve the existing Evidence-first canonical flow;
- collect sources incrementally;
- make processing idempotent under retries and overlapping input;
- persist per-Source checkpoints;
- persist typed work items, leases, retries, and dead-letter state;
- trigger research through a deterministic, versioned policy;
- recover safely after process interruption;
- integrate with the existing Research, Thesis, and Report chain;
- remain deployable as a single-machine modular monolith;
- keep Evidence, overrides, revisions, and audit history append-oriented;
- provide a PostgreSQL-compatible logical design without claiming SQL dialect
  portability in the first implementation.

---

## 6. Non-Goals

The following are explicitly out of scope for Phase 7. Implementations must not
include them as incidental "platform foundations":

- Kafka or a general event bus;
- a distributed workflow engine;
- Event Sourcing;
- a vector database as the system of record;
- a knowledge graph;
- an agent swarm or agent-controlled scheduler;
- automated trading or external action execution;
- a general web crawler;
- multi-tenancy;
- real-time tick market data;
- a general connector DSL or plugin framework;
- a complete UI;
- PyPI publication work;
- renaming the `src` package namespace;
- a separate top-level `src/signals` package;
- rewriting the existing reports subsystem;
- full provider coverage or unrestricted historical backfill.

These exclusions are acceptance constraints. A Phase 7 implementation that
depends on one of them must return to RFC review.

---

## 7. Architectural Principles

### 7.1 Evidence-first

A Signal may not enter the canonical research flow without Evidence grounding.
Cheap relevance filtering may happen before Evidence, but its outputs are
collection candidates, not canonical Signals.

### 7.2 Provider isolation

Connector-specific SDK types, HTTP responses, authentication, rate-limit
headers, and provider errors terminate inside `ingestion`. They must not appear
in `core`, `research`, or reports.

### 7.3 Deterministic control plane

Scheduling, retry, checkpoint movement, idempotency, leases, lifecycle, and
research-trigger decisions are controlled by deterministic code. An agent may
implement a bounded extraction or synthesis port, but cannot own work state or
select arbitrary runtime transitions.

### 7.4 Append-only provenance

Raw collection identity, Evidence revisions, curator overrides, trigger
decisions, and audit events must not lose history through overwrite. Mutable
operational projections may point to the current record, while prior records
remain queryable.

### 7.5 Modular monolith first

Phase 7 validates correctness in one process and one relational database.
Module boundaries remain explicit, but no network boundary is introduced
without measured operational need.

### 7.6 Durable before distributed

Restart recovery, duplicate processing, lease expiry, and transaction
correctness must be solved before introducing message infrastructure or
multiple services.

### 7.7 Domain, application, and infrastructure separation

- **Domain:** canonical research objects and their invariants.
- **Application:** collection, document processing, trigger policy, and report
  projection use cases.
- **Infrastructure:** HTTP/provider clients, SQLite, raw payload storage, and
  process scheduling.

Infrastructure models must not become canonical domain models by accident.

---

## 8. Proposed Architecture

```text
Scheduler
   → CollectionWorkItem
   → Connector.collect()
   → CollectionBatch
   → RawDocument persistence and deduplication
   → Normalization
   → EvidenceProducer
   → Evidence
   → SignalExtractor
   → Signal gates / promotion
   → ResearchTriggerPolicy
   → ResearchWorkItem
   → Existing Research / Thesis workflow
   → ReportQueryService
   → ReportInputProjection
   → Existing Report builders/renderers
```

### 8.1 Boundary responsibilities

**Scheduler**

- Enqueues due collection or report work.
- Does not call providers directly.
- Does not decide research meaning.

**Connector**

- Communicates with one provider family.
- Maps provider responses into `CollectionBatch`.
- Does not create Evidence, Signal, Research, Thesis, or Report objects.

**Ingestion service**

- Claims collection work, invokes a Connector, validates batch shape, persists
  raw records, applies dedupe, and advances checkpoints atomically.
- Does not interpret investment or research significance.

**Normalization and EvidenceProducer**

- Convert accepted RawDocuments into `CandidateObservation` and immutable
  Evidence with transformation provenance.
- Do not promote Signals or update Theses.

**Signal extraction and gates**

- Reuse the existing `SignalExtractor`, Signal invariants, gates, scoring, and
  lifecycle.
- Do not receive provider response objects.

**ResearchTriggerPolicy**

- Evaluates eligible Signals and existing open Research.
- Returns an auditable decision: ignore, hold, merge, or create work.
- Does not directly modify a Thesis.

**Durable work service**

- Atomically claims, leases, completes, retries, or dead-letters typed work.
- Does not contain provider mapping or research policy.

**ReportQueryService**

- Reads report-specific projections from repositories.
- Returns existing report input DTOs or a stable projection.
- Does not expose ORM rows to report builders.

---

## 9. Module Boundaries

The proposed layout follows the repository's existing top-level packages:

```text
src/
  ingestion/
    connector.py
    models.py
    service.py
    deduplication.py

  persistence/
    repositories/
    database/

  runtime/
    work.py
    checkpoints.py

  research/
    triggering.py
```

No top-level `src/signals` package is proposed. The canonical `Signal` remains
in `src/core/signals`.

### 9.1 `src/ingestion/connector.py`

- **Responsibility:** Connector and health-result ports.
- **Inputs:** `Source`, `IngestionCheckpoint`, collection limit, infrastructure
  configuration injected into the connector implementation.
- **Outputs:** `CollectionBatch`, optional `SourceHealth`.
- **Dependencies:** core `Source`, ingestion application models, standard
  Protocol types.
- **Must not depend on:** research, reports, Thesis, ORM rows, runtime queue
  implementations.

### 9.2 `src/ingestion/models.py`

- **Responsibility:** Provider-neutral collection envelopes.
- **Inputs:** Mapped provider results.
- **Outputs:** `RawDocument`, `CollectionBatch`, `IngestionCheckpoint` views.
- **Dependencies:** IDs and timestamps only where useful.
- **Must not depend on:** provider SDKs, research, reports, database models.

### 9.3 `src/ingestion/service.py`

- **Responsibility:** Collection and document-processing use cases and their
  transaction coordination.
- **Inputs:** claimed typed work, connectors, repository ports.
- **Outputs:** persisted document identities and subsequent work items.
- **Dependencies:** connector port, repository ports, work service.
- **Must not depend on:** concrete SQLite statements, report renderer, Thesis
  mutation.

### 9.4 `src/ingestion/deduplication.py`

- **Responsibility:** Deterministic key and fingerprint construction.
- **Inputs:** normalized identity and content fields.
- **Outputs:** typed keys/fingerprints.
- **Dependencies:** standard hashing and ingestion models.
- **Must not depend on:** network clients, database sessions, agents.

### 9.5 `src/persistence/repositories/`

- **Responsibility:** Narrow ports driven by actual Phase 7 use cases.
- **Inputs/outputs:** Domain or application models, query specifications, and
  explicit transaction handles where necessary.
- **Dependencies:** core/application types.
- **Must not depend on:** connectors or report formatting.

### 9.6 `src/persistence/database/`

- **Responsibility:** SQLite schema, migrations, transactions, repository
  implementations, and serialization.
- **Inputs/outputs:** Implements repository ports and the compatibility Store
  facade.
- **Dependencies:** SQLite standard library or an approved database library
  selected during implementation review.
- **Must not expose:** ORM rows or database connections to core, research, or
  reports.

### 9.7 `src/runtime/work.py`

- **Responsibility:** Typed durable work state and claiming semantics.
- **Inputs:** typed work commands and transaction-aware work repository.
- **Outputs:** claimed leases and explicit transition results.
- **Must not depend on:** provider SDKs or research interpretation.

### 9.8 `src/runtime/checkpoints.py`

- **Responsibility:** Application-level checkpoint validation and movement
  rules.
- **Must not independently commit:** checkpoint movement belongs to the
  collection transaction.

### 9.9 `src/research/triggering.py`

- **Responsibility:** Deterministic and versioned research-trigger decisions.
- **Inputs:** eligible Signals, open Research summaries, entity/topic context,
  priority policy, and dedupe state.
- **Outputs:** ignore, hold, merge, or create-work decisions.
- **Must not depend on:** connector, HTTP, SQLite implementation, or report
  rendering.

### 9.10 Detection package decision

A new `src/detection` package is **not required for the Phase 7 MVP**. The
existing `workflow.SignalExtractor` port and `research` promotion services are
sufficient. A later RFC may extract a detection package if multiple detector
implementations develop independent policies that no longer fit the workflow
adapter boundary.

---

## 10. Domain Model Additions

### 10.1 RawDocument

`RawDocument` is proposed as an application-level ingestion record, not a new
canonical research conclusion.

Proposed stable application fields:

```text
id
source_id
external_id
canonical_uri
published_at
retrieved_at
media_type
title
content_hash
raw_payload_ref
connector_name
connector_version
provider_metadata
schema_version
```

Field placement:

| Field | Placement | Reason |
|---|---|---|
| `id`, `source_id`, `external_id` | Application model | Stable identity and source lineage |
| `canonical_uri`, timestamps, media type, title | Application model | Provider-neutral normalization input |
| `content_hash` | Application model | Dedupe and integrity |
| `raw_payload_ref` | Application model as opaque reference | Enables retrieval without fixing storage technology |
| `connector_name`, `connector_version` | Application model | Reproducible collection lineage |
| `provider_metadata` | Bounded application envelope | Preserves non-canonical details without schema pollution |
| Database row version, storage path internals, compression | Infrastructure only | Not research semantics |
| Credentials, HTTP headers containing secrets | Neither model nor persistence record | Security boundary |

For the MVP, the canonical normalized content may be stored in SQLite when
bounded by a configured size. Large or binary raw payloads must be stored as
files under an operator-configured data directory, with `raw_payload_ref`,
content hash, size, and media type in SQLite. The database remains authoritative
for identity and lineage; the referenced payload remains immutable.

### 10.2 CollectionBatch

```text
records: tuple[RawDocumentCandidate, ...]
next_cursor: opaque string or null
collected_at: timestamp
provider_run_id: string or null
is_partial: boolean
retry_hint: typed optional hint
```

The cursor is opaque to application code. Only the corresponding connector may
interpret it. `is_partial` prevents checkpoint movement when the connector
cannot assert that the returned page is safely commit-complete.

### 10.3 IngestionCheckpoint

```text
source_id
cursor
watermark
last_success_at
connector_version
revision
```

`revision` supports optimistic concurrency. A checkpoint belongs to one Source
and connector contract version. A connector-version change that invalidates
cursor semantics requires an explicit reset or migration, never an implicit
reinterpretation.

### 10.4 WorkItem alternatives

#### Alternative A: Typed durable WorkItem

The runtime persists a common work envelope with a typed payload per kind:

```text
id
kind
payload
status
priority
attempt_count
available_at
lease_owner
lease_expires_at
idempotency_key
created_at
updated_at
last_error
```

MVP kinds:

```text
CollectionWorkItem
DocumentProcessingWorkItem
ResearchWorkItem
ReportWorkItem
```

Payloads must be schema-versioned and validated by kind. An unrestricted JSON
dictionary is not an acceptable application API.

#### Alternative B: ResearchRequest domain object

A separate ResearchRequest aggregate could model review, merging, rejection,
and a richer lifecycle independently of runtime execution.

#### Recommendation

Use **typed durable WorkItem** for Phase 7 MVP. Research triggering is a new
application workflow, but the repository does not yet demonstrate a need for a
long-lived ResearchRequest aggregate independent of execution. The trigger
decision log preserves intent and auditability. Promote ResearchRequest to a
domain object in a later RFC only if review, assignment, SLA, or cross-workflow
lifecycle requirements emerge.

### 10.5 WorkItem state model

Proposed states:

```text
pending → running → completed
    │         ├── retrying → pending
    │         └── dead_letter
    └── cancelled
```

A `running` item with an expired lease is reclaimable. Reclamation increments
the attempt count and records a failure/recovery event; it does not silently
reset history.

### 10.6 Evidence revision

The current correction capability is insufficient for continuous ingestion:
`Evidence.with_correction(new_content, reason)` creates a new object but does
not store `revision_of` or `reason`, and it retains the prior document hash.

Proposed eventual relation fields are:

```text
revision_of
supersedes
correction_reason
document_version
withdrawn_at
```

This RFC does **not** directly approve a breaking change to the existing
Evidence dataclass. Phase 7.1 must first choose one of:

1. additive optional Evidence fields with a schema-version migration; or
2. a separate append-only `EvidenceRevision` relation.

The recommended default is the separate relation for the MVP because it
preserves v0.1.0 object compatibility and distinguishes immutable Evidence
content from revision metadata. Any core schema modification requires the
version policy in `SPEC_VERSION.md` and `SCHEMA_EVOLUTION.md`.

---

## 11. Connector Contract

The proposed minimum port is:

```python
class Connector(Protocol):
    def collect(
        self,
        source: Source,
        checkpoint: IngestionCheckpoint | None,
        limit: int,
    ) -> CollectionBatch:
        ...
```

Connector responsibilities:

- provider communication;
- authentication through injected infrastructure configuration;
- pagination and provider cursor interpretation;
- rate-limit interpretation;
- mapping provider responses to provider-neutral candidates;
- classifying provider failures into bounded error categories.

Connector prohibitions:

- generating Signal objects;
- creating Research or ResearchWorkItem directly;
- modifying a Thesis;
- building a Report;
- committing a database checkpoint;
- logging credentials or authorization headers.

### 11.1 Healthcheck

```python
healthcheck(source: Source) -> SourceHealth
```

is **Should Have**, not a Must Have. MVP collection results already provide
last-success, latency, and provider-error state. A separate healthcheck should
be implemented only for providers with a cheap, documented readiness endpoint;
otherwise it duplicates live collection traffic and can distort rate limits.

---

## 12. Persistence Strategy

### 12.1 SQLite

Advantages:

- no external service for a single-machine deployment;
- transactions, indexes, foreign keys, and unique constraints are sufficient
  for the bounded MVP;
- deterministic temporary-database integration tests;
- simple backup and restart validation.

Risks:

- one writer at a time and lock contention under concurrent work;
- differences from PostgreSQL in types, locking, JSON, and work claiming;
- careless use of SQLite-specific SQL can make migration expensive.

### 12.2 PostgreSQL immediately

Advantages:

- stronger concurrent-write and row-locking behavior;
- mature constraints and operational queries;
- closer to a possible multi-worker deployment.

Risks:

- adds a service requirement to local development and CI;
- increases migration, provisioning, cleanup, and test complexity before
  workload characteristics are known;
- does not remove the need to design correct idempotency and leases.

### 12.3 Proposed choice

Use **SQLite as the Phase 7 MVP system of record**, with a
PostgreSQL-compatible logical design:

- explicit migrations;
- portable scalar types;
- normalized uniqueness keys;
- no correctness dependency on SQLite JSON query functions;
- short write transactions;
- bounded worker count, with one write-intensive worker by default;
- repository conformance tests that can later be reused for PostgreSQL.

"PostgreSQL-compatible" is a design constraint, not a claim that SQL files or
locking statements are interchangeable.

### 12.4 Store compatibility

The current `Store` remains a compatibility facade for existing runtime,
research, and tests. `InMemoryStore` remains available for unit tests.

New repository ports are introduced only for real Phase 7 queries:

- `RawDocumentRepository`: create-if-absent and fetch pending documents;
- `CheckpointRepository`: get and compare-and-set within collection
  transactions;
- `WorkRepository`: enqueue-if-absent, claim, transition, retry, dead-letter;
- `EvidenceRepository`: append and query by document/locator;
- `SignalRepository`: query by entity, status, time, Evidence, and fingerprint;
- `ResearchRepository`: query open Research by entity/topic and persist
  versioned changes;
- `ReportProjectionRepository`: bounded window and lineage reads;
- `AuditRepository`: append and query operational events.

The following must not remain in the production Store contract:

- whole-database `clear`;
- whole-database `snapshot`/`restore`;
- unbounded `list_*` as the primary production query;
- work queue, connector credential, and raw filesystem management hidden
  behind generic object CRUD.

Production backup/restore is an operational database concern, not a domain
Store method. Existing snapshot/restore remains for InMemoryStore compatibility
until a separate deprecation RFC is accepted.

---

## 13. Idempotency and Deduplication

Idempotency is defined at each boundary rather than by one global hash.

### 13.1 Collection idempotency

Primary key:

```text
source_id + external_id
```

If a provider has no stable external ID, the connector must derive and
version a deterministic external identity from canonical URI and provider
fields. A content hash alone is not document identity because legitimate
revisions can change content.

### 13.2 Content deduplication

Key:

```text
normalized content_hash
```

Content dedupe may relate two documents but must not erase their distinct
Source or retrieval provenance.

### 13.3 Evidence idempotency

Key:

```text
raw_document_id + locator + extraction_version
```

The locator is a canonical page/section/offset/time-series coordinate. An
extraction-version change may intentionally create new Evidence while retaining
lineage to the same RawDocument.

### 13.4 Signal idempotency

Proposed fingerprint:

```text
entity_id
+ normalized signal type
+ normalized falsifiable claim
+ sorted evidence_ids
+ event-time bucket
+ extractor/policy version
```

The fingerprint prevents retry duplicates, not semantically similar independent
events. Signal clustering remains a separate research concern.

### 13.5 Research trigger idempotency

Key:

```text
entity/topic key
+ sorted triggering signal cluster
+ trigger policy version
```

The transaction either finds and merges with an eligible open ResearchWorkItem
or inserts one unique work item.

### 13.6 Report idempotency

Key:

```text
report kind
+ normalized reporting window
+ entity/topic scope
+ input revision fingerprint
+ report schema/builder version
```

The same report input returns the existing run or an identical deterministic
artifact. Changed inputs create a new report run with lineage to the prior run.

### 13.7 Enforcement responsibilities

- Application code constructs canonical, versioned keys and explains their
  semantics.
- Database unique constraints provide the final race-safe guarantee.
- A uniqueness conflict is handled as an idempotent existing result only when
  the conflicting key and object kind match.
- Checkpoints advance only after related records and dedupe keys commit.
- Broad persistence exceptions must not be interpreted as duplicates.

---

## 14. Transaction Boundaries

### 14.1 Collection transaction

For one safely commit-complete page or batch, a single transaction performs:

```text
insert RawDocument identities/content references if absent
+ insert collection/deduplication records
+ enqueue DocumentProcessingWorkItems if absent
+ compare-and-set IngestionCheckpoint
+ append collection audit result
```

The checkpoint is updated last within the transaction, but all operations
commit atomically. If any operation fails, none is visible. A partial batch
does not move the safe checkpoint unless the connector contract provides a
separate confirmed resume cursor for the committed subset.

Network collection happens outside the write transaction. The transaction
revalidates the checkpoint revision before commit; a stale collector must
discard or idempotently reconcile its batch.

### 14.2 Evidence production transaction

For one RawDocument or bounded chunk:

```text
append Evidence if idempotency key is absent
+ append transformation provenance
+ append EvidenceRevision relation when applicable
+ enqueue signal-evaluation work if absent
+ mark DocumentProcessingWorkItem completed
```

Evidence content and its transformation provenance commit together. Raw payload
file writing must complete and be hash-verified before the database transaction
records its reference. Orphan-file cleanup is an operational job; the database
must never reference an incomplete file.

### 14.3 Work claiming transaction

Claiming performs atomically:

1. select one eligible `pending` or `retrying` item whose `available_at` is due,
   or one `running` item whose lease expired;
2. verify it is still claimable;
3. set `status=running`, `lease_owner`, and `lease_expires_at`;
4. increment `attempt_count`;
5. append a claim/audit record;
6. return the claimed item.

SQLite implementation uses a short write transaction and a conditional update
on ID, prior status, and revision. A second worker that updates zero rows did
not claim the item and must retry selection.

Completion is a conditional transition from `running` by the current lease
owner. A transient failure clears the lease, sets `retrying`, computes
`available_at`, and records the error. Exhaustion sets `dead_letter`. An
expired lease is recoverable; it is never a permanent lock.

### 14.4 Research trigger transaction

For one trigger decision:

```text
append trigger decision
+ find eligible open ResearchWorkItem by dedupe key
+ merge signal IDs with optimistic concurrency, or insert unique work item
+ mark signal-cluster evaluation work completed
```

The unique trigger key and conditional revision update prevent two workers from
creating or overwriting the same research work.

### 14.5 Thesis and Research updates

Phase 7 must not use unconditional overwrite when concurrent workers could
touch the same Research or Thesis. Repository writes require expected revision
or equivalent compare-and-set semantics. On conflict, the work retries from
fresh state; it does not merge interpretations implicitly.

---

## 15. Runtime Model

### 15.1 Alternatives

**A. Whole-cycle batch**

Closest to v0.1.0, but recovery is coarse, all Sources are rescanned, and slow
collection extends the entire cycle.

**B. Modular monolith with durable staged work**

Keeps one deployment while making work incremental, leased, queryable, and
restart-safe. It adds database state but avoids distributed delivery semantics.

**C. External event-driven architecture**

Supports independent scaling but introduces duplicate delivery, ordering,
event-schema, deployment, and observability costs before throughput requires
them.

**D. Agent-controlled workflow**

Can help with bounded interpretation, but is unsuitable for deterministic
checkpoint, lease, retry, and lifecycle control.

### 15.2 Proposed choice

Choose **B: modular monolith with durable staged work**.

MVP work granularity:

- collect one source page or bounded batch;
- process one document;
- evaluate one bounded Evidence batch;
- evaluate one Signal cluster;
- execute one ResearchWorkItem;
- generate one report.

### 15.3 Compatibility with current cycle orchestration

The existing six-stage Pipeline remains valid and continues to serve current
tests and synchronous use. Migration proceeds by adapters:

1. Collection and Evidence stages may initially run through an existing
   Pipeline with a prepared `PipelineContext`.
2. Durable work handlers invoke bounded workflow ports for one document or
   cluster.
3. The whole-cycle scheduler becomes a compatibility command and report
   aggregation boundary, not the only unit of recovery.
4. Existing stage semantics and gates are not deleted merely to fit the new
   work queue.

Any proposal to remove or reorder the six stages requires a separate workflow
RFC.

---

## 16. Research Trigger Policy

Inputs:

```text
verified or active Signals
existing open Research summaries
entity/topic context
priority policy
deduplication state
```

Outputs:

```text
ignore(reason)
hold(reason, review_required)
merge(target_work_or_research_id, signal_ids)
create ResearchWorkItem(payload)
```

Every decision records:

- policy name and version;
- triggering Signal IDs and fingerprints;
- entity/topic key;
- decision and reason codes;
- priority inputs and result;
- timestamp and correlation ID;
- whether a curator override was applied.

MVP policy rules are deterministic configuration and code. They may use Signal
status, score thresholds already approved by existing specifications, entity
scope, cluster membership, and presence of open Research. They may not allow a
single draft Signal to update a Thesis.

The lineage remains:

```text
Signal → trigger decision → ResearchWorkItem → Research → Thesis
```

### 16.1 Human review

MVP requires a persisted `hold` outcome and operator ability to inspect it, but
does not require a full review UI. A minimal command or application API may
promote or reject held work using the existing append-only override pattern.
Automatic review is the default for deterministic pass cases; mandatory manual
review of every Signal is not proposed.

---

## 17. Report Integration

Reports must not import ORM or database implementation types.

Proposed boundary:

```text
ReportQueryService
    → ReportInputProjection
    → existing DailyBriefInputs / WeeklyReviewInputs / PerEntityBriefInputs
    → existing builder
    → existing renderer/exporter
```

The query service supports bounded:

- reporting-window queries using event and detected timestamps explicitly;
- entity/topic queries;
- Signal → Evidence → Source lineage queries;
- Research and Thesis revisions effective in the window;
- report-run identity and prior-run lookup.

`ReportRun` is operational metadata containing run ID, idempotency key, input
fingerprint, builder/schema versions, status, timestamps, and artifact
references. It is not a replacement for the existing `Report` model.

The current report JSON schema does not change merely because inputs come from
SQLite. Adding Evidence-level provenance fields to exported JSON requires an
explicit backward-compatible schema proposal and version bump.

---

## 18. Observability

The MVP requires structured logs and queryable database state, not a complete
monitoring platform.

### 18.1 Connector metrics/state

- last successful collection;
- collection latency;
- records collected;
- records deduplicated;
- provider errors by category;
- rate-limit state and next allowed attempt;
- checkpoint age and revision.

### 18.2 Pipeline conversion counters

- RawDocument → Evidence;
- Evidence → Signal;
- Signal → ResearchWorkItem;
- ResearchWorkItem → Research;
- rejected, held, and zero-output counts at each boundary.

### 18.3 Work queue state

- pending;
- running;
- retrying;
- dead-letter;
- oldest pending age;
- expired leases;
- attempts and processing latency by work kind.

### 18.4 Failure records

At minimum:

```text
work_item_id
stage
error_category
error_message
attempt
occurred_at
source_id
correlation_id
```

Error messages must be sanitized. Structured categories drive retry policy;
free-form message text does not.

---

## 19. Security and Configuration

- Connector credentials are infrastructure configuration, never fields on
  `Source`, RawDocument, Evidence, or work payloads.
- Secrets are read from environment variables or an operator-owned local
  configuration source excluded from version control.
- Tokens, authorization headers, cookies, and signed URLs are redacted from
  logs and persisted provider metadata.
- `Source` describes the logical information origin. Provider endpoint,
  credential reference, timeout, and rate-limit configuration belong to a
  separate infrastructure mapping keyed by Source or connector configuration
  ID.
- Raw payloads are treated as potentially sensitive. Storage location,
  retention, file permissions, maximum size, and logging rules are configured.
  Payload bodies are not written to routine logs.
- Every HTTP connector configures connect/read timeout, bounded response size,
  maximum retries, rate limits, and a project-identifying user agent where
  provider policy requires it.
- Source and redirect destinations are allowlisted. Connectors must not become
  arbitrary URL fetchers.
- Retry limits are finite. Authentication and malformed-request errors are not
  blindly retried.
- No enterprise secrets platform is required for the single-machine MVP.

---

## 20. MVP Scope

The target implementation window is 4–8 weeks.

### Must Have

1. RSS connector.
2. Deterministic file/fixture connector representing filing documents.
3. Unified RawDocument envelope.
4. SQLite durable backend with explicit migrations.
5. Per-Source checkpoint.
6. Layered deduplication and idempotency keys.
7. Typed database-backed work queue with leases, retry, and dead letter.
8. Evidence-first document processing.
9. Deterministic and versioned ResearchTriggerPolicy.
10. Restart recovery.
11. Structured operational state and logs.
12. Integration with existing Research and reports.

### Should Have

- bounded backfill;
- manual hold/reject through a minimal application interface;
- Evidence correction/revision relation;
- Source health backoff;
- ReportRun identity;
- simple supports/contradicts stance in research reasoning.

### Later

- real SEC network connector;
- PostgreSQL backend;
- multiple concurrent worker processes;
- event bus or external workflow engine;
- semantic/vector index as a derived projection;
- knowledge graph;
- agent planning;
- streaming market data;
- broader connector catalog;
- UI and notifications;
- multi-tenancy;
- package namespace migration.

---

## 21. Connector Selection

The first Phase 7 implementation uses:

1. **RSS connector**
2. **Deterministic file/fixture filing connector**

### 21.1 RSS

RSS validates:

- polling and conditional incremental retrieval;
- feed-item external identity;
- overlapping feed-window deduplication;
- publication and retrieval timestamps;
- a common small-document flow.

### 21.2 Deterministic file/fixture filing connector

The fixture filing connector validates:

- authoritative document provenance;
- larger documents;
- amendments and revisions;
- stable external IDs and locators;
- repeatable integration and failure tests without live Internet dependence.

### 21.3 Why SEC is not one of the first two

A live SEC connector adds provider policy, user-agent, rate-limit, network, and
test stability concerns at the same time as the persistence and recovery
foundation. It is the preferred third connector after the fixture contract and
revision behavior pass acceptance tests. This sequencing does not make the
fixture connector a permanent substitute for authoritative production data.

---

## 22. Testing Strategy

### 22.1 Unit tests

- connector response mapping;
- cursor and partial-batch behavior;
- canonical URI and dedupe key construction;
- content and Signal fingerprints;
- Evidence idempotency keys;
- typed payload validation;
- work state transitions and lease rules;
- retry classification;
- ResearchTriggerPolicy decisions and policy-version recording;
- checkpoint compare-and-set.

### 22.2 Integration tests

- SQLite repository conformance;
- foreign keys and unique constraints;
- transaction rollback;
- checkpoint not advancing on rollback;
- restart recovery from a file-backed SQLite database;
- duplicate input and uniqueness races;
- lease expiry and reclaim;
- retry exhaustion and dead letter;
- Evidence revision/correction handling;
- Store compatibility facade;
- bounded report projection queries.

### 22.3 End-to-end test

At least one deterministic scenario must execute:

```text
collect fixture
→ persist RawDocument
→ produce Evidence
→ produce grounded Signal
→ create ResearchWorkItem
→ run existing Research path
→ build and render report
```

Running the same scenario twice must not create duplicate canonical objects.
Restarting between stages must complete the same logical result.

### 22.4 Failure tests

- provider timeout;
- provider rate limit;
- partial batch;
- duplicate provider response;
- malformed document;
- oversized payload;
- database failure before checkpoint commit;
- process restart with a running lease;
- stale checkpoint revision;
- retry exhaustion;
- unavailable raw payload reference.

Live Internet access must not be the only validation path. Connector contract
tests use captured or constructed fixtures.

---

## 23. Migration Plan

### Phase 7.0 — RFC and ADR freeze

- Review and accept this RFC.
- Resolve the seven foundation questions.
- Record the accepted foundation in ADR-007.
- Determine schema and SPEC_VERSION impact before implementation.

### Phase 7.1 — Ingestion foundation

- application models;
- connector port;
- file/fixture connector;
- RSS connector contract with offline fixtures;
- dedupe functions;
- checkpoint semantics.

### Phase 7.2 — Durable persistence

- SQLite migrations and repositories;
- Store compatibility facade;
- typed durable work items;
- claiming, lease, retry, and dead-letter state;
- restart tests.

### Phase 7.3 — Evidence integration

- RawDocument → CandidateObservation/Evidence adapter;
- transformation provenance;
- approved correction relation;
- Evidence and Signal idempotency.

### Phase 7.4 — Research triggering

- ResearchTriggerPolicy;
- trigger decision log;
- ResearchWorkItem creation and merge;
- optimistic Research/Thesis updates where concurrency applies.

### Phase 7.5 — End-to-end continuous run

- scheduled collection;
- bounded staged handlers;
- restart recovery;
- report query projection and report-run identity;
- operational counters and failure queries.

Each subphase must be independently testable. The full architecture must not be
implemented in a single change.

---

## 24. Backward Compatibility

- v0.1.0 core objects are preserved unless a separately reviewed schema change
  supplies migration and version policy.
- `InMemoryStore` remains for unit tests and existing consumers.
- Existing six-stage Pipeline tests are retained. Staged work adds adapters
  rather than deleting the cycle path.
- Current report builders, renderers, and JSON schema do not change solely due
  to database integration.
- SQLite repositories return domain/application objects, not ORM rows.
- The `src` public namespace is not migrated in Phase 7.
- Existing lifecycle transitions and invariant enforcement remain authoritative.
- New serialized application models and work payloads include schema versions.
- Database schema changes use ordered migrations. No migration is inferred from
  Python dataclass shape at runtime.

The decision freeze itself requires no SPEC_VERSION bump: it changes no schema,
invariant, runtime behavior, or production code. Phase 7 implementation is
expected to require a SPEC_VERSION **MINOR** bump when new backward-compatible
schemas and documents become active. Any future change to Evidence semantics,
existing workflow contracts, or invariants must be reassessed under
`SPEC_VERSION.md`; a breaking schema change may require a MAJOR bump and
migration window.

---

## 25. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| One-time rewrite of Store breaks all consumers | Keep Store as compatibility facade; introduce repositories incrementally by real query |
| Connector types pollute research | Enforce Connector → CollectionBatch boundary and dependency tests |
| Checkpoint advances before data commit | Commit raw records, dedupe keys, work enqueue, and checkpoint in one transaction |
| Duplicate Evidence | Unique key on document + locator + extraction version; append-only create |
| Duplicate Signal | Versioned deterministic fingerprint plus database uniqueness |
| Queue loses tasks | Persist work and transitions in SQLite; restart and rollback tests |
| Lease deadlock | Finite expiry, owner-conditional completion, reclaim path, audit each recovery |
| Broad exception swallowing hides failure | Catch explicit uniqueness/idempotency errors only; classify and retry or abort other failures |
| SQLite write contention | Short transactions, bounded worker count, WAL evaluation, operational lock metrics, PostgreSQL exit criteria |
| Evidence correction is ambiguous | Prefer explicit append-only revision relation; do not silently mutate Evidence |
| `src` namespace is awkward for distribution | Record as existing debt; exclude rename from Phase 7; handle in separate RFC |
| Report provenance remains too shallow | Add lineage query and ReportRun now; version exported schema before adding fields |
| Provider raw data contains secrets or sensitive content | Redaction, bounded metadata, restricted payload storage, retention configuration |
| Scope expands to platform work | Enforce Non-Goals and 4–8 week Must Have list during review |
| Agent control-plane creep | Agents implement bounded ports only; deterministic code owns work and state |
| Work payload becomes untyped JSON | Per-kind versioned payload schemas and validation |
| Connector version invalidates cursor | Store connector version with checkpoint; require explicit reset/migration |
| Concurrent Research/Thesis overwrite | Repository compare-and-set and retry from fresh state |

---

## 26. Alternatives Considered

### 26.1 New top-level `src/signals`

Rejected because canonical Signal already exists under `src/core/signals`.
A second package would blur domain, extraction, scoring, and ingestion
responsibilities.

### 26.2 Event-first, Evidence-later

Rejected because it permits ungrounded Signals and conflicts with existing
Evidence invariants. A pre-Evidence relevance candidate is allowed but is not a
Signal.

### 26.3 Kafka or event bus first

Rejected for Phase 7 because the immediate problems are durable state,
idempotency, and transactions. A broker would add delivery semantics without
removing those problems.

### 26.4 Agent workflow first

Rejected as the control plane because checkpointing, leases, retries, and
lifecycle must be deterministic and auditable. Agents remain eligible as
bounded port implementations.

### 26.5 PostgreSQL first

Not selected for MVP because it adds service and CI complexity before concurrent
workload requires it. The logical schema is constrained to preserve a later
PostgreSQL path.

### 26.6 Event Sourcing

Rejected because full aggregate reconstruction from events is not required.
Append-only audit and revision records provide the required history with lower
operational complexity.

### 26.7 Vector database as primary store

Rejected because vector similarity does not provide relational constraints,
transactional checkpoints, uniqueness, or authoritative provenance. A vector
index may later be derived from relational records.

### 26.8 Direct Connector → Research

Rejected because it leaks provider semantics, bypasses immutable Evidence and
Signal gates, and weakens lineage.

### 26.9 Whole-cycle batch only

Retained for compatibility but rejected as the sole Phase 7 runtime because
recovery and retry granularity are too coarse for continuous collection.

---

## 27. Approved Decisions

The following decisions were frozen on 2026-07-25. They authorize Phase 7.1 to
begin within the scope of this RFC. They do not authorize Phase 7.2 database
implementation or any change to existing domain schemas.

### 27.1 Architecture

**Accepted:** Phase 7 uses a modular monolith with durable staged work and
retains the canonical Evidence-first flow. Provider isolation, deterministic
control-plane behavior, and repository boundaries remain mandatory. A general
event bus and agent-controlled runtime are not part of Phase 7.

### 27.2 Database

**Accepted:** SQLite is the Phase 7.2 MVP durable persistence backend.
Phase 7.1 does not implement a database. Persistence access remains behind
repository boundaries, and the logical design must preserve a later
PostgreSQL migration path.

### 27.3 Connector strategy

**Accepted:** The Phase 7 MVP connectors are:

1. RSS Connector.
2. Deterministic Filing Fixture Connector.

The fixture connector provides repeatable offline validation. Phase 7.1 does
not integrate a live SEC provider, and required tests do not depend on live
Internet access.

### 27.4 WorkItem model

**Accepted:** Phase 7 uses typed WorkItems rather than introducing a
first-class `ResearchRequest` domain aggregate. Initial types are:

```text
CollectionWorkItem
DocumentProcessingWorkItem
ResearchWorkItem
```

WorkItem is the cross-stage task abstraction. Each kind requires a typed,
versioned payload; an untyped JSON container is not an acceptable application
contract.

### 27.5 Evidence revision strategy

**Deferred with direction:** Phase 7.1 does not modify the Evidence schema.
The intended direction is an append-only `EvidenceRevision` object or relation
that preserves the original Evidence and full correction history. Its final
schema requires a separate RFC or ADR and the applicable schema-version review.

### 27.6 Human Signal review

**Deferred:** Phase 7 MVP does not require a mandatory human review gate.
Signal promotion uses Evidence grounding, confidence, importance, and a
deterministic policy. A mandatory human gate may be proposed later using
operational results.

### 27.7 Raw payload strategy

**Accepted:** The database stores metadata plus bounded normalized content or
an immutable payload reference. Large PDF, HTML, or other raw blobs are stored
outside the core database and addressed by an integrity-checked reference.

### 27.8 Report schema

**Deferred:** Phase 7 does not modify the existing Report schema. The supported
flow remains:

```text
Ingestion
  → Evidence
  → Research
  → Existing Reports
```

Any exported provenance schema change requires a separate RFC.

### 27.9 Resolution history

The original questions and recommended defaults are preserved below as design
history; none remains an authorization blocker for Phase 7.1.

| Original question | Resolution | Frozen outcome |
|---|---|---|
| Q1: SQLite MVP system of record | Accepted | SQLite in Phase 7.2; no database implementation in Phase 7.1 |
| Q2: Initial connectors | Accepted | RSS plus deterministic filing fixture |
| Q3: Typed WorkItem or ResearchRequest | Accepted | Typed WorkItem; no first-class ResearchRequest |
| Q4: Evidence correction representation | Deferred with direction | No Phase 7.1 Evidence change; append-only revision design later |
| Q5: Mandatory human Signal review | Deferred | Not mandatory in Phase 7 MVP |
| Q6: Raw payload storage | Accepted | Metadata/normalized content or reference in DB; large raw payload external |
| Q7: Report provenance schema | Deferred | Existing Report schema unchanged |

Historical recommended defaults:

1. SQLite with explicit migrations, repository conformance tests, and a
   documented PostgreSQL exit path.
2. RSS and deterministic filing fixture before a live SEC connector.
3. Typed WorkItem plus append-only trigger decision log.
4. Separate append-only Evidence revision relation.
5. Persisted hold capability without mandatory review of every Signal.
6. Bounded normalized content in the database and large/binary payloads in
   external immutable storage.
7. Internal lineage queries without changing exported Report JSON in Phase 7.

---

## 28. Acceptance Criteria

Phase 7 is complete only when:

- the RSS and deterministic filing fixture connectors both run through the
  same Connector contract;
- duplicate collection does not create duplicate RawDocument, Evidence,
  Signal, ResearchWorkItem, or ReportRun records;
- process restart resumes pending work and reclaims expired leases;
- checkpoint movement cannot lose successfully returned but uncommitted data;
- work items support finite retry and durable dead-letter state;
- every canonical Signal references at least one persisted Evidence;
- Research is created or merged only through a recorded deterministic trigger
  decision;
- a draft Signal cannot directly modify a Thesis;
- the existing Research and Report flows continue to work;
- file-backed SQLite data is readable after application restart;
- transaction rollback, duplicate input, and lease expiry integration tests
  pass;
- the end-to-end offline fixture test passes;
- Python 3.10–3.13 CI remains green;
- existing unit tests are not deleted merely to accommodate Phase 7;
- no Phase 7 Non-Goal is introduced as an implementation dependency;
- migrations and serialized payloads have explicit versions;
- security tests or assertions confirm credentials and tokens are absent from
  domain objects, work payloads, and logs.

---

## 29. Decision Summary

| Decision | Frozen choice | Status |
|---|---|---|
| Architecture | Modular monolith + durable staged work | Accepted |
| Canonical flow | Evidence-first | Accepted |
| Database | SQLite for Phase 7.2 MVP; none in Phase 7.1 | Accepted |
| Persistence evolution | Repository ports + Store compatibility facade | Accepted |
| Queue | Typed database-backed work items with leases | Accepted |
| Signal model | Reuse existing core Signal | Accepted |
| Research request | Typed ResearchWorkItem; no first-class ResearchRequest | Accepted |
| Connector count | Two | Accepted |
| Initial connectors | RSS + deterministic filing fixture | Accepted |
| Evidence correction | No Phase 7.1 schema change; append-only relation direction | Deferred |
| Human Signal review | Not mandatory in Phase 7 MVP | Deferred |
| Raw payload | DB metadata/normalized content or reference; large raw payload external | Accepted |
| Report schema | Existing schema unchanged | Deferred |
| Event bus | Deferred | Accepted |
| Agent control plane | Rejected for Phase 7 | Accepted |
| Vector DB / knowledge graph | Deferred | Accepted |
| Package namespace rename | Deferred to separate RFC | Accepted |

---

## Trade-offs

This proposal gains restart safety, traceable external input, bounded
incremental work, and race-safe idempotency while preserving the v0.1.0 domain
chain. It accepts SQLite write-concurrency limits, additional application
models, explicit migrations, and the operational responsibility of managing a
database file and optional raw-payload directory.

It deliberately gives up early distribution and dynamic agent orchestration.
If future measured throughput exceeds the modular monolith, the typed work and
repository boundaries provide evidence for a narrower extraction.

---

## Consequences

As a consequence of acceptance:

- Phase 7 implementation begins with ingestion and durability, not new research
  semantics.
- Database schema and transaction review become required for each staged
  checkpoint.
- Runtime work identity becomes more granular than the current cycle.
- Existing Store consumers remain supported during migration.
- Connector implementations become replaceable without provider types
  reaching research.
- New operational state must be retained and queryable.
- A later PostgreSQL implementation must satisfy repository conformance rather
  than mimic SQLite internals.

---

## Affected Documents

Implementation is expected to require the following updates in separate
reviewed changes. The decision freeze itself changes none of them:

| Document | Proposed change type |
|---|---|
| `docs/IMPLEMENTATION_ROADMAP.md` | Add accepted Phase 7 checkpoints |
| `docs/03_RUNTIME_MODEL.md` | Add durable staged-work and restart semantics |
| `docs/02_WORKFLOW_MODEL.md` | Clarify bounded invocation compatibility; no stage reorder proposed |
| `docs/01_OBJECT_MODEL.md` | Add only approved application/domain relations |
| `docs/INFRASTRUCTURE_SPECIFICATION.md` | Add SQLite, payload storage, and continuous-run topology |
| `SCHEMA_EVOLUTION.md` | Apply existing rules to new serialized models |
| `SPEC_VERSION.md` | Record approved version impact |
| `GLOSSARY.md` | Add Connector, RawDocument, checkpoint, lease, and work-item terms |
| `RFC/README.md` | Add RFC-001 to index when submitted per governance |

This decision freeze intentionally modifies none of those documents.

---

## Affected Schemas

| Schema | Current version | Future implementation target | Bump type |
|---|---:|---:|---|
| Existing Evidence | Existing v0.1.0 implementation / spec-defined schema | Unchanged by default | None unless Open Question 4 changes |
| Existing Signal | Existing v0.1.0 implementation / spec-defined schema | Unchanged | None |
| Existing Report JSON | 1.0 | Unchanged by default | None |
| RawDocument | None | 1.0.0 | New schema |
| CollectionBatch | None | 1.0.0 | New schema |
| IngestionCheckpoint | None | 1.0.0 | New schema |
| Typed WorkItem payloads | Current runtime-only cycle WorkItem | New durable schema 1.0.0 | New application schema; compatibility adapter required |
| TriggerDecision | None | 1.0.0 | New schema |
| ReportRun | None | 1.0.0 | New operational schema |

Exact schema versions are finalized only after RFC acceptance and schema review.

---

## Affected Invariants

The accepted architecture preserves existing invariants, especially Evidence
grounding, provenance, stable identity, lifecycle discipline, append-only
override history, and cycle/audit traceability.

Phase 7 constraints such as transactional checkpoint movement and
idempotent work may become implementation invariants. Whether they are promoted
to system-wide numbered invariants requires a separate governance review.
Adding or changing a numbered invariant triggers the SPEC_VERSION rules and is
not silently approved by this decision freeze.

---

## SPEC_VERSION Impact

- **Current SPEC_VERSION:** 1.3.0
- **Decision-freeze target:** unchanged at 1.3.0
- **Future implementation target:** 1.4.0 if all additions are
  backward-compatible
- **Future implementation bump type:** MINOR

This assessment changes to MAJOR if review approves a breaking Evidence schema,
changes an existing invariant, or breaks workflow/agent contracts.

---

## Glossary Impact

Terms to add when their schemas or implementation become active:

- Connector
- RawDocument
- CollectionBatch
- IngestionCheckpoint
- idempotency key
- content fingerprint
- lease
- CollectionWorkItem
- DocumentProcessingWorkItem
- ResearchWorkItem
- TriggerDecision
- ReportRun

No existing term is deprecated by this RFC.

---

## References

- [Architecture Principles](../docs/00_ARCHITECTURE_PRINCIPLES.md)
- [Object Model](../docs/01_OBJECT_MODEL.md)
- [Workflow Model](../docs/02_WORKFLOW_MODEL.md)
- [Runtime Model](../docs/03_RUNTIME_MODEL.md)
- [Infrastructure Specification](../docs/INFRASTRUCTURE_SPECIFICATION.md)
- [Report Specification](../docs/REPORT_SPECIFICATION.md)
- [Implementation Roadmap](../docs/IMPLEMENTATION_ROADMAP.md)
- [Governance](../GOVERNANCE.md)
- [Specification Versioning](../SPEC_VERSION.md)
- [Schema Evolution](../SCHEMA_EVOLUTION.md)
- [System Invariants](../INVARIANTS.md)
- [ADR-004: Override append-only](../ADR/ADR-004-override-append-only.md)
- [ADR-006: Decay worker](../ADR/ADR-006-decay-worker.md)

---

**Decision-freeze state:** RFC accepted, not committed in this working tree;
Phase 7.1 authorized to begin; implementation not started; code changes none.
