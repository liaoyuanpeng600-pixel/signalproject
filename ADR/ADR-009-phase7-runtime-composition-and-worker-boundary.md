# ADR-009: Phase 7 Runtime Composition and WorkItem Worker Boundary

> **Status:** accepted
> **Date:** 2026-07-26
> **Accepted Date:** 2026-07-26
> **Acceptance Note:** The project owner reviewed and accepted the composition,
> worker ownership, five-state lifecycle, claim authority, renewal boundary,
> retry-policy ownership, audit scope, connector registry, and at-least-once
> idempotency decisions recorded below. RFC-001 and ADR-008 remain
> authoritative.
> **Supersedes:** None
> **Superseded by:** None
> **Related RFC:** RFC-001
> **Related ADRs:** ADR-007, ADR-008

## Context and Problem Statement

Phase 7.2 completed the file-backed SQLite persistence slice:

- ordered, checksummed migrations;
- document, deduplication, checkpoint, and pending WorkItem repositories;
- atomic collection persistence;
- restart, rollback, schema, contract, and compatibility coverage.

The adapters are not yet composed into an application process. No production
caller constructs `SQLiteDatabase`, runs migrations, or supplies
`SQLiteAtomicCollectionPersistence` to collection orchestration. Persisted
WorkItems are pending records only; there is no durable acquisition,
transition, lease, retry, dead-letter, dispatch, or worker lifecycle.

This ADR records the accepted boundary between process composition, collection
orchestration, persistence, scheduling, and future WorkItem workers. It does
not itself implement that boundary. In particular, it does not change the frozen
Phase 7.1 ingestion contracts or the frozen Phase 7.2 persistence contracts.

## Existing System Evidence

### Accepted authority

- RFC-001 accepts a modular monolith with durable staged work, typed WorkItems,
  finite leases, owner-conditional completion, retry, and durable dead-letter
  state.
- ADR-007 accepts the three WorkItem kinds:
  `CollectionWorkItem`, `DocumentProcessingWorkItem`, and `ResearchWorkItem`.
- ADR-008 keeps Phase 7 WorkItems separate from `runtime.WorkItem` and
  `runtime.WorkQueue`. It defers executable claim, lease, retry, cancellation,
  and dead-letter behavior to a separate worker/lease decision and migration.
- ADR-008 requires connector I/O outside the collection write transaction,
  checkpoint compare-and-set inside that transaction, short SQLite write
  transactions, stable worker identity, finite leases, owner-checked
  transitions, attempt increments, and reclaim of expired work.

The RFC roadmap originally grouped worker lifecycle work under Phase 7.2.
ADR-008 and the completed Phase 7.2 implementation deliberately narrowed that
slice to pending-only persistence and required a later decision and migration.
This is a sequencing refinement, not a semantic conflict: the accepted worker
requirements remain future requirements.

### Implemented flow

`CollectionRunner` is a deterministic, side-effect-free application service:

1. `prepare_collection_work` creates a deterministic `CollectionWorkItem`.
2. `collect` validates source and connector binding.
3. The connector produces a bounded `CollectionBatch`.
4. `deduplicate_documents` produces accepted and duplicate decisions.
5. The runner creates deterministic `DocumentProcessingWorkItem` values for
   accepted documents.
6. The runner returns `CollectionRunResult`.

Separately, `SQLiteAtomicCollectionPersistence.commit_collection` can atomically:

1. insert or resolve documents and identity claims;
2. create document-processing work for the command's valid subset;
3. compare-and-set the checkpoint;
4. return canonical counts and the stored checkpoint.

No production component currently converts `CollectionRunResult` into a
`CollectionCommitCommand` and invokes that port.

### Existing runtime is a compatibility path

The current `src/runtime` package implements a different, whole-cycle runtime:

- `runtime.queue.WorkItem` represents cycle execution, not a Phase 7 typed
  payload;
- `WorkQueue` and `DeadLetterQueue` are in-process collections;
- `DefaultScheduler` and `CycleDispatcher` feed `PipelineExecutor`;
- `RuntimeCycle` loads and writes domain objects through the broad `Store`;
- current retry orchestration creates a fresh cycle WorkItem rather than
  conditionally transitioning a durable typed WorkItem.

Construction sites for `CollectionRunner`, `RuntimeCycle`, `WorkQueue`, and
`DefaultScheduler` are tests. The package has no production CLI, command,
startup hook, connector registry, or database configuration entry point.
`Store` and `InMemoryStore` remain the compatibility persistence path for the
existing pipeline, research, reports, and their tests.

### Missing flow

The following are planned, not implemented:

- process-level database configuration and migration startup;
- a coordinator from collection execution to `CollectionPersistencePort`;
- durable WorkItem acquisition and lifecycle transitions;
- typed handler dispatch;
- RawDocument-to-Evidence integration;
- bounded ResearchWorkItem execution;
- worker polling, shutdown, retry, dead-letter, and crash recovery;
- a connector registry and process entry point.

## Decision Scope

This ADR defines:

- the intended composition root and dependency direction;
- the collection coordination boundary;
- ownership of database and migration lifecycle;
- the minimum future worker lifecycle port;
- the accepted WorkItem state machine;
- claim, lease, concurrency, and crash-recovery rules;
- typed dispatch responsibilities;
- an incremental Phase 7.3 plan.

This ADR does not:

- add or change Python contracts;
- select production configuration syntax or a CLI framework;
- approve a database migration;
- implement workers, handlers, scheduling, or transitions;
- replace the existing runtime, `Store`, or `InMemoryStore`;
- introduce `CollectionRepository`;
- add a WorkItem kind or payload schema version.

## Accepted Composition Design

### Process composition root

Use `src/composition.py` as the initial process-level composition root.
This is the only accepted production module allowed to import both
infrastructure implementations such as `src.persistence.sqlite` and
application/runtime abstractions.

The composition root is not a service locator. It constructs an immutable
object graph once per process or command and passes dependencies explicitly.
Objects do not discover a global database or read global configuration.

An eventual executable command may call the composition root, but command-line
parsing and process entry points are outside the immediate composition
milestone.

### Configuration

The caller supplies an explicit immutable configuration value containing at
least:

- SQLite file path;
- busy timeout;
- WAL preference;
- migration compatibility policy already supported by the adapter;
- later, worker identity, polling interval, per-kind lease duration, and retry
  policy.

The database path is a `Path` supplied by the outer process boundary. It is not
derived inside a repository, connector, runner, or domain object. Tests supply
temporary file paths or non-SQLite fakes.

Secrets and provider configuration remain outside WorkItem payloads and are
resolved by the composition-owned connector or handler registry.

Composition owns the concrete connector registry and its configuration
binding. The registry is explicitly constructed and injected. Duplicate
registrations fail startup, a requested missing connector fails clearly, and
name/version lookup preserves checkpoint binding validation. The registry
does not dynamically import or discover arbitrary connectors and is never
module-global mutable state. Milestone 3.1 may define narrowly scoped immutable
configuration DTOs without reopening these ownership or failure rules.

### Database and migration lifecycle

For one process or bounded command:

1. the composition root constructs one `SQLiteDatabase` configuration object;
2. it runs `migrate(database)` synchronously before constructing services or
   starting polling;
3. it constructs the existing SQLite repositories and
   `SQLiteAtomicCollectionPersistence`;
4. it injects only persistence-neutral ports into application services;
5. startup fails closed on migration compatibility or checksum failure.

`SQLiteDatabase` remains a connection factory, not a long-lived shared
connection. Each repository read and public transaction opens a configured
short-lived connection and closes it through its existing context manager.
Connections are never shared concurrently across threads.

Shutdown first stops accepting or claiming work, then lets an active handler
finish within a bounded grace period. A process that cannot finish does not
force an unowned completion; its finite lease eventually permits reclaim.
There is no database connection pool or singleton to close in the current
adapter design.

### Collection coordination

Keep `CollectionRunner` unchanged and side-effect-free. It should not receive a
database or persistence port directly.

Introduce, in a later implementation milestone, an application-level
`CollectionCoordinator` that receives:

- `CollectionRunner`;
- `CollectionPersistencePort`;
- `CheckpointRepository` for the pre-I/O checkpoint read;
- an explicitly supplied connector and `Source` (a registry may resolve them
  at a higher boundary).

The coordinator:

1. reads the current checkpoint;
2. prepares collection work;
3. calls `CollectionRunner.collect`;
4. rejects a partial or invalid batch before persistence;
5. builds `CollectionCommitCommand` from the complete result;
6. invokes `CollectionPersistencePort.commit_collection`;
7. returns an application result without exposing adapter types.

This design answers the dependency requirement without changing the public
`CollectionRunner` constructor: the coordinator receives both runner and port,
and the runner remains reusable in pure unit tests. Tests can inject a fake
`CollectionPersistencePort` and fake checkpoint repository. Existing
`Store`/`InMemoryStore` consumers need no adaptation.

### Collection transaction boundary

Connector network or file I/O, payload validation, and deterministic work
derivation occur before the transaction.

The transaction starts inside
`CollectionPersistencePort.commit_collection(command)` and ends when that
call commits or raises. The concrete atomic adapter owns exactly one write
transaction. The coordinator must not begin a transaction, pass a connection,
or call component repositories to reconstruct atomicity.

Checkpoint CAS failure rolls back documents, identities, and requested work
from that invocation. The coordinator reloads and recollects; it must not
weaken CAS or report a replay as successful.

## Accepted Worker Ownership Model

### Responsibility split

| Layer | Responsibility | Must not own |
|---|---|---|
| Persistence | durable selection, atomic claims, revision/CAS, leases, transitions, attempt/error records | handler choice, external I/O, retry policy interpretation |
| Runtime | orchestration, typed dispatch, outcome classification, observability | SQL, SQLite connections, transaction syntax |
| Worker | execute exactly one acquired item under a claim, renew only when necessary, report one outcome | polling cadence, global scheduling, direct row mutation |
| Scheduler | due-time polling cadence, capacity/backpressure, shutdown signals | business execution, transition SQL, payload interpretation |
| Composition | construct concrete adapters, registries, policies, clock, worker identity | hidden global lookup, runtime business decisions |

The existing cycle `WorkQueue`, cycle `WorkItem`, retry orchestrator, and
in-process DLQ are not adapters for this lifecycle. They remain compatibility
components until separately retired.

### Minimum future contract surface

Do not extend the frozen pending-only `WorkItemRepository`. Use a separate
`WorkItemLifecyclePort` with explicit DTOs and operations equivalent to:

- `claim_next(...) -> WorkClaim | None`;
- `renew_lease(...) -> WorkClaim`;
- `complete(...) -> WorkTransitionResult`;
- `fail_retryable(...) -> WorkTransitionResult`;
- `fail_terminal(...) -> WorkTransitionResult`.

The exact Python signatures, keyword rules, DTO fields, error hierarchy, and
clock representation require a contract-freeze review before implementation.

`WorkClaim` minimally carries the canonical typed WorkItem, stable worker
identity, fresh unpredictable opaque claim/lease token, lease expiry, attempt
count, and revision.
Callers receive no SQLite row, connection, exception, or transaction object.
SQLite row identifiers must not be used or exposed as claim tokens.

`renew_lease` is part of the future lifecycle contract. It requires `running`
status, current owner, current token, expected revision, and an unexpired
current lease. The periodic heartbeat mechanism belongs to later
scheduler/process-lifecycle work, not persistence. Milestone 3.1 implements
neither renewal nor heartbeat. Before production scheduling is enabled,
long-running handler and renewal behavior require explicit tests.

Persistence atomically records attempts, lifecycle state, revisions, lease
fields, and transition timestamps. Runtime classifies execution outcomes as
success, retryable failure, or terminal failure. An immutable injected retry
policy determines the maximum attempt count, exhaustion evaluation, retry
delay, and backoff/scheduling behavior within the frozen `dead_letter`
terminal destination; composition owns the concrete configured policy.
Persistence validates and atomically records transition inputs but does not
classify failures or trust stale claim authority.

## Accepted WorkItem State Machine

The smallest viable durable states are:

- `pending`: created, not yet acquired;
- `running`: owned by one unexpired claim;
- `retrying`: released after a retryable failure and unavailable until due;
- `completed`: terminal success;
- `dead_letter`: terminal failure or retry exhaustion.

Cancellation is excluded from the Phase 7.3 MVP. There is no `cancelled`
state, cancel operation, cancellation metadata, or cancellation-specific
scheduler behavior. Cancellation requires a future, separately approved
architecture decision.

### State invariants

| State | Lease | Attempt | Availability | Terminal |
|---|---|---:|---|---|
| `pending` | none | 0 | claimable when due | no |
| `running` | owner, token, finite expiry | >= 1 | not independently selectable before expiry | no |
| `retrying` | none | >= 1 | claimable when due | no |
| `completed` | none | >= 1 | not claimable | yes |
| `dead_letter` | none | >= 1 | not claimable without a separately approved replay API | yes |

Every successful mutation increments `revision` exactly once and records
canonical UTC timestamps. Terminal rows are immutable through the lifecycle
port.

### Transitions

| Source | Destination | Trigger | CAS and lease rule | Failure and recovery |
|---|---|---|---|---|
| `pending` | `running` | scheduler asks for one due item | short write transaction; condition on ID, `pending`, due `available_at`, and revision; set owner/fresh token/expiry; increment attempt exactly once and advance revision; record claimed/updated time | zero updated rows means claim lost and does not increment attempt; select again after bounded delay |
| `retrying` | `running` | retry delay has elapsed | same as pending claim, additionally condition on `retrying`; new token and finite lease; increment attempt exactly once | competing or stale worker gets no claim and does not increment attempt |
| `running` | `running` | justified lease renewal | current owner, opaque token, unexpired lease, and expected revision must match; extend expiry and increment revision | stale/expired owner loses authority; handler must not publish completion |
| `running` | `running` | atomic reclaim after lease expiry | condition on expired lease, prior running status, and revision; replace owner with a fresh token/expiry; increment attempt exactly once and advance revision; record recovery metadata | failed/stale reclaim does not increment attempt; old owner becomes stale after successful reclaim |
| `running` | `completed` | handler reports success | current owner, token, unexpired lease, and expected revision; clear lease, set completed/updated time, increment revision | stale completion is rejected; domain-side idempotency must tolerate re-execution after uncertain outcome |
| `running` | `retrying` | runtime classifies a retryable failure below attempt budget | owner/token/revision check; clear lease; set sanitized error and future `available_at`; increment revision | item is dormant until due; crash before transition leaves it recoverable by lease expiry |
| `running` | `dead_letter` | terminal failure or attempt exhaustion | owner/token/revision check; clear lease; record sanitized terminal category and dead-letter time; increment revision | terminal and not automatically replayed |

An expired `running` row may be reclaimed directly in one transaction. A
separate visible `retrying` transition is not required for crash recovery.
Every successful atomic claim, including a due `pending` or `retrying` claim,
increments `attempt_count` exactly once. Every successful expired-lease
reclaim also increments it exactly once. A claim or reclaim that loses its
conditional update, is stale, or otherwise fails does not increment the
counter. Lease renewal does not increment it. These counter semantics are
authoritative from RFC-001 and ADR-008 and are not deferred to Milestone 3.2.
Milestone 3.2 freezes only retry policy: maximum attempts, the point and
mechanics of exhaustion evaluation, backoff/scheduling, and retryable versus
terminal error classification. The accepted lifecycle already requires
terminal failures and exhausted work to end in `dead_letter`; Milestone 3.2
does not introduce another terminal state.

### Idempotency and uncertain outcomes

Claims provide at-least-once execution, not exactly-once external side effects.
The worker must assume that it can execute again after a crash between a
domain commit and WorkItem completion.

- collection remains protected by document/work identities and checkpoint CAS;
- document processing needs a deterministic Evidence/provenance identity and
  atomic domain-write/completion boundary or an equivalent outbox-style
  reconciliation;
- research execution needs deterministic Research lineage and revision/CAS.

Document processing must use stable document/work identities and idempotent
Evidence writes. Research execution must use stable WorkItem/research
identities and idempotent research outputs. A stale claimant cannot transition
the lifecycle row after losing authority, but downstream writes may already
have succeeded before lease loss is detected. Replay safety therefore cannot
depend only on the WorkItem lifecycle row. Exact downstream ports and output
identities must be frozen before Milestone 3.5 implementation; this does not
block Milestone 3.1 collection composition.

## Execution Dispatch

Dispatch is an exhaustive mapping from the three frozen WorkItem DTO types.
Unknown kinds or payload schema versions are compatibility failures and are
never guessed or silently upgraded.

### CollectionWorkItem

- **Handler:** resolve the configured `Source` and matching connector, then call
  `CollectionCoordinator`.
- **Input:** source ID, connector name/version, complete optional checkpoint,
  and limit.
- **Downstream boundary:** `CollectionRunner`,
  `CheckpointRepository`, and `CollectionPersistencePort`.
- **Success:** canonical `CollectionCommitResult`, followed by owner-checked
  WorkItem completion.
- **Retryable examples:** connector timeout/rate limit, transient transport
  failure, SQLite busy/operational failure, checkpoint conflict after reload
  and recollection.
- **Terminal examples:** unknown connector/version, missing or invalid Source,
  incompatible payload schema, invariant or provenance violation.
- **Idempotency:** typed WorkItem `(kind, idempotency_key)`, application-owned
  document IDs, deduplication identities, and checkpoint CAS.

The collection WorkItem being executed and the document-processing WorkItems
created by its commit have distinct identities. Completing the former is a
future lifecycle transition, not part of the frozen collection commit.

### DocumentProcessingWorkItem

- **Handler:** load the canonical RawDocument and invoke a future bounded
  document-to-Evidence application port.
- **Input:** `raw_document_id`.
- **Downstream boundary:** `DocumentRepository` plus a not-yet-frozen
  `DocumentProcessingPort`; existing Evidence/Store behavior may be adapted
  behind that port.
- **Success:** durable Evidence and transformation provenance, followed by
  owner-checked WorkItem completion.
- **Retryable examples:** transient payload-store access, temporary model or
  service failure, operational persistence contention.
- **Terminal examples:** missing document or immutable payload, hash mismatch,
  unsupported schema/media type, deterministic validation failure.
- **Idempotency:** RawDocument ID plus a deterministic Evidence/provenance key.
  The exact Evidence commit contract remains unresolved and must not be
  improvised by the worker.

### ResearchWorkItem

- **Handler:** load and revalidate the referenced eligible Signals, then invoke
  a future bounded research execution port using existing research services.
- **Input:** entity ID, canonical signal IDs, and topic key.
- **Downstream boundary:** a not-yet-frozen `ResearchExecutionPort` adapted to
  current Store/research services.
- **Success:** durable Research lineage and result, followed by owner-checked
  WorkItem completion.
- **Retryable examples:** transient model/provider failure, temporary
  persistence contention, bounded dependency outage.
- **Terminal examples:** missing entity, permanently ineligible or invalid
  signal set, incompatible payload, deterministic policy rejection.
- **Idempotency:** WorkItem identity plus deterministic Research lineage and
  optimistic revision/CAS.

## Concurrency and Crash Recovery

- SQLite claiming uses one short serialized write transaction, compatible with
  `BEGIN IMMEDIATE`; external handler work never occurs inside it.
- Selection and conditional update form one atomic claim operation.
- A stable process/worker identity and a new opaque token identify each claim.
- Every completion, failure, and renewal is conditional on owner, token,
  unexpired lease, status, and expected revision.
- Lease expiry uses canonical UTC values. A supplied clock is used in tests;
  business code does not call SQLite time functions as its clock abstraction.
- A process crash before a claim commit produces no claim. A crash after claim
  commit leaves `running` work reclaimable after expiry.
- A successful reclaim replaces authority and increments attempt/revision
  exactly once. A resurrected old process cannot complete or fail the item.
  Failed or stale claim/reclaim attempts update neither attempt nor revision.
- Milestone 3.2 freezes maximum attempts, exhaustion evaluation and
  dead-letter transition details, retry scheduling/backoff, and outcome
  classification. It does not reopen the `dead_letter` destination or
  claim-time/reclaim-time counter semantics.
- Polling uses bounded delay and jitter outside persistence to avoid a busy
  loop. Scheduler capacity limits the number of concurrently executing items.
- SQLite remains suitable for the initial one-write-intensive-worker
  deployment. Measured claim contention or write latency, rather than API
  redesign, triggers PostgreSQL evaluation.

## Configuration and Lifecycle Rules

- Configuration is immutable process input assembled at the outer boundary;
  repositories, runners, handlers, and domain objects do not read environment
  variables or command-line arguments.
- The database path is explicit and file-backed. Tests may instead inject
  persistence-neutral fakes where restart behavior is not under test.
- Migrations complete successfully before any collection or worker activity.
  Compatibility or checksum failure aborts startup.
- One process owns one constructed dependency graph. `SQLiteDatabase` remains
  a factory for short-lived configured connections, not a shared connection.
- Connector and handler registries are constructed explicitly and are
  immutable after startup. Unknown names or versions fail closed.
- A future scheduler stops polling before shutdown waits on active handlers.
  During the grace period, only the current claim owner may transition work.
- If execution exceeds the grace period, the process does not forge success or
  clear ownership. Recovery occurs through finite lease expiry and conditional
  reclaim.
- Runtime policy supplies a stable worker identity, canonical UTC clock,
  bounded polling interval, concurrency limit, lease duration, attempt budget,
  and retry delay. Persistence stores and enforces transition inputs but does
  not invent policy.
- No migration, connection, thread, worker, or polling loop starts as a module
  import side effect.

Milestone 3.2 must freeze the exact maximum attempts, lease duration, renewal
interval, initial and maximum retry delay, backoff multiplier, jitter behavior,
exhaustion evaluation and `dead_letter` transition details, and
retryable/non-retryable classification. ADR-009 intentionally defines no
numeric defaults for these parameters. Successful-claim and
successful-reclaim counter increments and the `dead_letter` terminal
destination are already frozen and are not policy parameters.

## Dependency Direction Rules

Allowed direction:

```text
process entry point
  -> composition root
     -> runtime/application orchestration
        -> ingestion and persistence-neutral ports
           -> core/domain models
     -> concrete SQLite adapters (construction only)
```

Rules:

- domain, ingestion DTOs, and persistence ports do not import runtime or
  SQLite;
- runtime and handlers depend on ports and typed DTOs, never concrete SQLite;
- SQLite adapters implement ports and may import DTOs/errors, never runtime;
- only the composition root chooses concrete adapters;
- connector implementations do not receive a database;
- private connection-scoped SQLite helpers remain private;
- `Store` is not expanded with ingestion or lifecycle methods;
- no service locator, global connection, global repository registry, or
  module-import migration side effect is permitted.

## Schema Implications

The current `work_items` table is intentionally pending-only:

- `CHECK (status = 'pending')`;
- `CHECK (revision = 0)`;
- no claim, owner, lease, attempt, terminal, or error columns.

The accepted lifecycle therefore requires an ordered, checksummed migration
after contract approval. A likely SQLite migration rebuilds `work_items` while
preserving every existing pending row and its typed payload.

Minimum lifecycle schema direction, with exact column design deferred:

- widened status constraint for the five accepted states;
- mutable non-negative `revision`;
- `attempt_count`;
- `lease_owner`, opaque `lease_token`, and `lease_expires_at`;
- `claimed_at`, `completed_at`, and `dead_lettered_at`;
- sanitized `last_error_category` and bounded `last_error_message`.

`available_at`, `priority`, `created_at`, and `updated_at` already exist.
Candidate indexes are:

- `(status, available_at, priority, created_at)` for due selection;
- `(status, lease_expires_at)` for reclaim.

An append-only lifecycle audit table is not required for the MVP. The
structured transition-audit requirement from ADR-008 is preserved through
structured operational observability emitted by later runtime/scheduler work
and the durable current transition metadata. An append-only audit table
remains a compatible future migration requiring separate justification.

Whether maximum attempts is stored per row or supplied by immutable runtime
policy is frozen in Milestone 3.2. No migration may be written before the
exact lifecycle contract, retry policy, and compatibility matrix are approved.

## Compatibility Requirements

- Phase 7.1 DTOs, connectors, identity semantics, and `CollectionRunner` remain
  unchanged.
- Phase 7.2 ports, errors, result DTOs, adapters, schema, and migrations remain
  unchanged until a separately approved lifecycle migration.
- `WorkItemRepository.insert/get` remains the pending creation/read boundary;
  lifecycle operations use a separate port.
- `CollectionPersistencePort.commit_collection` retains its exact signature
  and atomic semantics.
- `Store` and `InMemoryStore` remain valid for the existing pipeline and as
  dependencies behind future handler adapters.
- Existing `runtime.WorkItem`, `WorkQueue`, scheduler, retry, and DLQ behavior
  remains available but is not reused for durable typed work.
- SQLite-specific values never cross application-facing contracts.
- Python 3.10 through 3.13 compatibility remains required by project metadata
  and CI.
- File-backed SQLite remains required for restart and migration tests.

## Alternatives Considered

### Inject persistence directly into CollectionRunner

Rejected because the runner is currently deterministic and explicitly avoids
persistence and domain mutation. A coordinator preserves that contract and
keeps pure tests small.

### Use the broad Store as the composition and queue boundary

Rejected by ADR-008. It would couple ingestion/lifecycle methods to existing
domain consumers and weaken transaction-specific contracts.

### Reuse runtime.WorkItem, WorkQueue, retry, and DeadLetterQueue

Rejected because those types represent whole-cycle, in-process execution and
do not carry the frozen typed payload, durable identity, CAS, or lease
semantics. ADR-008 explicitly separates them.

### Add claim/complete methods to WorkItemRepository

Rejected because it would drift the frozen pending-only Phase 7.2 port.
A separate lifecycle port makes the new state machine reviewable.

### Hold one process-wide SQLite connection

Rejected because the existing adapter safely configures short-lived
connections and forbids concurrent connection sharing. A global connection
also obscures transaction ownership.

### Run migrations lazily in each repository

Rejected because startup compatibility failures must occur before work begins.
Migration ownership belongs to the composition root.

### Perform connector I/O inside the collection transaction

Rejected by RFC-001 and ADR-008 because it holds the SQLite write lock across
unbounded external I/O.

### Treat claims as exactly-once delivery

Rejected because process failure makes at-least-once execution unavoidable.
Correctness comes from leases, owner/CAS checks, and domain idempotency.

### Add cancellation, generic CRUD, ORM, async APIs, or an external broker now

Rejected as unnecessary for the smallest viable modular-monolith worker and
outside the frozen Phase 7 scope.

## Accepted Milestone Sequence

### Milestone 3.1: Existing collection persistence composition

- **Objective:** construct the completed SQLite slice and connect collection
  execution to the frozen atomic port through a coordinator.
- **Allowed scope:** `src/composition.py`, an application-level collection
  coordinator module, narrow configuration DTOs, package exports, and focused
  tests.
- **Prerequisites:** approval of the composition portions of this ADR.
- **Exclusions:** process CLI, polling, claims, lifecycle schema, handlers for
  document/research work, scheduler, and Store changes.
- **Tests:** pure coordinator tests with fakes; SQLite integration for complete,
  empty, partial, conflict, rollback, and restart cases; import boundaries.
- **Gate:** connector I/O is outside the transaction; one atomic port call owns
  all writes; existing suites remain green.

### Milestone 3.2: Worker lifecycle contract freeze

- **Objective:** approve exact lifecycle states, DTOs, port signatures, errors,
  clock/lease rules, retry-policy parameters, outcome classification, and
  structured observability requirements. Claim/reclaim counter increments are
  already frozen and are not reopened.
- **Allowed scope:** persistence-neutral contract modules, contract tests,
  exports, and documentation needed to freeze exact policy semantics.
- **Prerequisites:** accepted ADR-009.
- **Exclusions:** SQL, migrations, concrete repositories, worker loop, handlers.
- **Tests:** signature, DTO invariant, state-transition, dependency, and
  adapter-neutral contract tests.
- **Gate:** frozen, unambiguous contracts and policies with no SQLite type or
  speculative numeric value left unresolved.

### Milestone 3.3: Work lifecycle schema migration

- **Objective:** add the minimum durable columns, constraints, and indexes
  needed by the frozen lifecycle contract while preserving pending rows.
- **Allowed scope:** next ordered SQLite migration and migration/schema tests.
- **Prerequisites:** Milestone 3.2.
- **Exclusions:** claiming repository and runtime behavior.
- **Tests:** fresh database, upgrade from v0001, checksum/reopen, rollback,
  row preservation, constraint/index/FK inspection, supported Python versions.
- **Gate:** both fresh and upgraded databases match the approved schema without
  destructive loss.

### Milestone 3.4: SQLite claiming and transition adapter

- **Objective:** implement the lifecycle port with atomic claim, renewal,
  completion, retryable failure, terminal failure, and expired-lease reclaim.
- **Allowed scope:** one SQLite lifecycle adapter, exports, contract and focused
  SQLite tests.
- **Prerequisites:** Milestones 3.2 and 3.3.
- **Exclusions:** handlers, polling scheduler, domain execution.
- **Tests:** two-connection races, CAS loss, owner/token enforcement, expiry,
  reclaim, attempt exhaustion, rollback, restart, and error translation.
- **Gate:** no double ownership; stale owners cannot mutate; all failure paths
  preserve a valid durable state.

### Milestone 3.5: Worker execution and typed dispatch

- **Objective:** execute one claim through exhaustive typed dispatch and report
  one lifecycle outcome.
- **Allowed scope:** worker runtime, handler protocols/adapters, classification
  policy, focused tests; downstream ports only after separate contract review.
- **Prerequisites:** Milestone 3.4 and approved document/research idempotency
  boundaries.
- **Exclusions:** polling cadence, multi-worker process supervision, new kinds,
  cancellation.
- **Tests:** each kind's success/retryable/terminal path, unknown payload,
  lease loss during execution, duplicate execution, and sanitized errors.
- **Gate:** one acquired item has one classified outcome; stale claims cannot
  publish lifecycle success.

### Milestone 3.6: Scheduler and process lifecycle

- **Objective:** add bounded polling, capacity, worker identity, graceful
  shutdown, and observability around the one-item executor.
- **Allowed scope:** scheduler/process runtime, configuration, composition, and
  lifecycle tests.
- **Prerequisites:** Milestone 3.5.
- **Exclusions:** distributed coordinator, external broker, autoscaling, UI.
- **Tests:** idle polling without busy-looping, backpressure, shutdown while
  idle/active, startup migration failure, signal handling, and restart.
- **Gate:** deterministic startup/shutdown and no abandoned permanent lock.

### Milestone 3.7: Recovery, concurrency, and end-to-end validation

- **Objective:** prove collection through downstream durable work under
  restart, contention, replay, and injected failures.
- **Allowed scope:** integration/e2e fixtures, operational documentation, and
  only demonstrated corrective changes.
- **Prerequisites:** Milestone 3.6.
- **Exclusions:** new capability, schema redesign, broker, PostgreSQL.
- **Tests:** kill/restart after claim and domain commit, expired reclaim,
  competing workers, retry exhaustion, dead-letter, checkpoint conflict,
  file close/reopen, and full compatibility suite.
- **Gate:** accepted Phase 7.3 completion audit with all frozen suites green and
  no duplicate authoritative domain result.

## Consequences and Risks

### Positive consequences

- infrastructure selection remains at one explicit boundary;
- collection orchestration becomes durable without contaminating the pure
  runner;
- frozen pending insertion stays stable while lifecycle evolves separately;
- SQLite transaction ownership remains visible and testable;
- worker crash recovery is deterministic rather than in-memory;
- current synchronous runtime and in-memory tests continue to function.

### Costs and risks

- a coordinator and lifecycle port add explicit types and tests;
- SQLite lifecycle migration requires a table rebuild and careful upgrade
  coverage;
- at-least-once execution requires downstream idempotency contracts not yet
  present;
- lease duration and clock skew can cause duplicate execution or slow recovery;
- direct reclaim can conceal repeated crashes unless structured transition
  observability and metrics are adequate;
- two runtime WorkItem concepts will coexist temporarily and require precise
  naming;
- the top-level composition root is a new architectural seam and must not grow
  into business logic.

## Acceptance Criteria

The project owner accepted this ADR on 2026-07-26 after approving:

- `src/composition.py` as the concrete infrastructure selection point and an
  explicitly injected `CollectionCoordinator`;
- an unchanged, persistence-free `CollectionRunner` and one frozen atomic port
  call whose transaction excludes connector work and command construction;
- the five-state lifecycle and direct atomic expired-lease reclaim;
- exclusion of cancellation from the Phase 7.3 MVP;
- combined owner, unpredictable opaque per-claim token, and expected revision
  transition authority;
- exactly one attempt increment for every successful claim or reclaim, and no
  increment for failed, stale, or conflicting attempts;
- `renew_lease` in the future lifecycle port, with periodic heartbeat owned by
  later scheduler/process work;
- persistence/runtime/retry-policy/composition responsibility boundaries;
- mutable current lifecycle state without a required append-only audit table;
- composition-owned explicit connector registry and fail-closed registration;
- at-least-once execution and downstream domain idempotency requirements;
- the Milestone 3.1 through 3.7 sequence and gates.

Acceptance of this ADR authorizes planning, not all implementation at once.
Each milestone still requires its own scoped instruction and validation.

## Unresolved Governance Decisions

No unresolved decision blocks ADR-009 acceptance or Milestone 3.1 collection
composition.

The following deliberately deferred retry-policy parameters must be frozen in
Milestone 3.2 before lifecycle schema or adapter implementation:

- maximum attempt count;
- exhaustion evaluation and `dead_letter` transition details;
- lease duration and renewal interval;
- initial and maximum retry delay;
- backoff multiplier and jitter behavior;
- retryable/non-retryable error classification;
- exact lifecycle port signatures, DTO fields, errors, and clock representation;
- whether the maximum attempt budget is stored per row or supplied by
  immutable policy.

Claim/reclaim counter behavior is not deferred: each successful atomic claim
or expired-work reclaim increments `attempt_count` exactly once; failed,
stale, or conflicting attempts do not increment it.

The exact document-to-Evidence and ResearchWorkItem-to-Research ports, output
identities, and idempotent commit behavior must be frozen before Milestone 3.5.
They do not block Milestone 3.1.

Excluded from the Phase 7.3 MVP are cancellation, an append-only lifecycle
audit table, arbitrary connector discovery, a service locator, global adapter
or connection state, a generic transaction manager, and reuse of the legacy
cycle WorkItem queue as the durable typed-work lifecycle.

## References

- [RFC-001: Durable Ingestion and Research Triggering](../RFC/RFC-001-durable-ingestion-research-triggering.md)
- [ADR-007: Phase 7 Foundation Decisions](ADR-007-phase7-foundation-decisions.md)
- [ADR-008: Phase 7 Persistence Decisions](ADR-008-phase7-persistence-decisions.md)
- `src/ingestion/service.py`
- `src/ingestion/work.py`
- `src/persistence/ingestion/ports.py`
- `src/persistence/ingestion/models.py`
- `src/persistence/sqlite/`
- `src/runtime/`
- `src/persistence/store.py`
- `src/persistence/in_memory.py`
