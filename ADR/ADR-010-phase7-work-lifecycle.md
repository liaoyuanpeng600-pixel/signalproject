# ADR-010: Phase 7 Durable WorkItem Lifecycle Contract

> **Status:** accepted
> **Date:** 2026-07-26
> **Accepted Date:** 2026-07-26
> **Acceptance Note:** The project owner completed the Milestone 3.2
> architecture review and accepted the five-state lifecycle, attempt and
> revision semantics, exact persistence-neutral port and DTO surface, claim
> authority, lease boundary, configurable retry policy, exhaustion behavior,
> failure taxonomy, clock and token boundaries, state invariants,
> observability requirements, compatibility matrix, and contract-test gates.
> **Supersedes:** None
> **Superseded by:** None
> **Related RFC:** RFC-001
> **Related ADRs:** ADR-007, ADR-008, ADR-009
> **Milestone:** Phase 7.3 Milestone 3.2

## Context

ADR-009 accepts the ownership boundary and five-state lifecycle for durable
Phase 7 WorkItems, but deliberately leaves the exact persistence-neutral
contract and retry policy to Milestone 3.2. The pending-only Phase 7.2
`WorkItemRepository` cannot implement that lifecycle, and no lifecycle schema
migration may be designed until the contract is frozen.

This record specifies the contract that a later schema migration and adapter
must implement. It does not add executable Python contracts, SQL, migrations,
repositories, workers, handlers, heartbeat, polling, process startup, or
connector registration.

The following accepted decisions are not reopened:

- the three Phase 7.1 typed WorkItems remain unchanged;
- lifecycle operations use a separate port rather than extending
  `WorkItemRepository`;
- states are `pending`, `running`, `retrying`, `completed`, and
  `dead_letter`;
- cancellation is excluded;
- every successful claim or expired-lease reclaim increments
  `attempt_count` exactly once;
- renewal does not increment `attempt_count`;
- every successful lifecycle mutation increments `revision` exactly once;
- transition authority requires the current worker ID, opaque claim token,
  expected revision, `running` status, and an unexpired lease;
- claims provide at-least-once execution;
- terminal rows cannot be replayed through this port.

## Decision Status

This ADR is the accepted Milestone 3.2 contract freeze.

Acceptance authorizes Milestone 3.3 schema planning. It does not implement or
authorize lifecycle schema, adapter, or runtime behavior as part of this
documentation-only milestone.

## Contract Placement and Dependency Direction

A later implementation will place the persistence-neutral lifecycle contract
under `src.persistence.ingestion`, alongside the existing Phase 7 persistence
ports, models, and errors. The exact module split may be:

```text
src/persistence/ingestion/lifecycle.py
src/persistence/ingestion/lifecycle_errors.py
```

The contract may import:

- `Protocol`, `TypeAlias`, and standard-library dataclass/enum types;
- `ID`;
- the three frozen Phase 7.1 WorkItem DTOs;
- the existing `IngestionWorkItem` type alias;
- the existing persistence error base.

It must not import:

- `sqlite3` or `src.persistence.sqlite`;
- `src.runtime`;
- connector implementations;
- `Store` or `InMemoryStore`;
- worker, handler, scheduler, composition, or process-startup modules.

Concrete adapters implement the port. Runtime consumes the port. Neither side
owns the other's policy decisions.

Token generation is a construction-time dependency of a concrete lifecycle
adapter through this persistence-neutral source:

```python
class ClaimTokenSource(Protocol):
    def new_token(self) -> str: ...
```

Composition injects the source. Production uses a cryptographically secure
implementation; tests use a deterministic fake. The port does not expose the
source on individual commands, and persistence does not access hidden global
randomness.

## Lifecycle Vocabulary

### WorkItemStatus

The contract defines a string enum with exactly these values:

```python
class WorkItemStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    RETRYING = "retrying"
    COMPLETED = "completed"
    DEAD_LETTER = "dead_letter"
```

No alias, `cancelled` state, arbitrary string status, or adapter-specific state
is accepted.

### WorkItemKind

The lifecycle kind enum has exactly these values and maps exhaustively to the
frozen DTO union:

```python
class WorkItemKind(str, Enum):
    COLLECTION = "collection"
    DOCUMENT_PROCESSING = "document_processing"
    RESEARCH = "research"
```

Unknown kinds and unsupported payload schema versions are compatibility
failures. They are never guessed, coerced, skipped as successful, or dispatched
to a generic handler.

### Claim authority

Claim authority is the tuple:

```text
work_item_id
worker_id
claim_token
expected_revision
```

Possession of a WorkItem ID, worker ID, or token alone is insufficient.

`worker_id` is stable for one worker instance, non-empty UTF-8 text, at most
128 characters, and contains only ASCII letters, digits, `.`, `_`, `:`, or
`-`. A restarted worker uses a new worker ID.

`claim_token` is obtained from the injected `ClaimTokenSource` during the
atomic claim/reclaim operation. A production token contains at least 256 bits
of cryptographic entropy and is encoded as an opaque URL-safe string without
padding. It is never a row ID, revision, timestamp, worker ID, deterministic
hash, counter, or caller-supplied command value. It must never appear in logs,
metrics, error messages, or audit fields.

## Exact Data Transfer Objects

All DTOs are frozen dataclasses with `slots=True`. Command and result DTOs are
also `frozen=True`. They expose application values only, never rows,
connections, cursors, SQL errors, or transaction handles.

### WorkClaimRequest

```python
@dataclass(frozen=True, slots=True)
class WorkClaimRequest:
    worker_id: str
    allowed_kinds: tuple[WorkItemKind, ...]
    claimed_at: str
    policy: WorkLifecyclePolicy
```

Rules:

- `allowed_kinds` is non-empty and contains no duplicate;
- tuple order is not a priority signal;
- `claimed_at` is a canonical, timezone-aware UTC ISO-8601 string;
- `policy` is the immutable policy defined below;
- the adapter selects at most one item.

### WorkClaim

```python
@dataclass(frozen=True, slots=True)
class WorkClaim:
    work_item: IngestionWorkItem
    kind: WorkItemKind
    worker_id: str
    claim_token: str
    claimed_at: str
    lease_expires_at: str
    attempt_count: int
    revision: int
    reclaimed: bool
    prior_worker_id: str | None
```

Rules:

- `work_item` is one of the three frozen Phase 7.1 DTOs;
- `kind` must match its DTO type;
- `attempt_count >= 1` and `revision >= 1`;
- `lease_expires_at` is strictly later than `claimed_at`;
- `reclaimed=False` requires `prior_worker_id=None`;
- `reclaimed=True` requires a non-empty `prior_worker_id`;
- the claim represents durable `running` state after the claim transaction
  commits.

After a renewal, `reclaimed` and `prior_worker_id` continue to describe how the
current execution grant began; renewal does not turn a reclaimed grant into an
ordinary first claim.

### Claim-bound commands

Every transition command repeats the full claim authority instead of accepting
a mutable claim object:

```python
@dataclass(frozen=True, slots=True)
class ClaimAuthority:
    work_item_id: ID
    worker_id: str
    claim_token: str
    expected_revision: int

@dataclass(frozen=True, slots=True)
class RenewLeaseCommand:
    authority: ClaimAuthority
    renewed_at: str
    lease_duration_seconds: int

@dataclass(frozen=True, slots=True)
class CompleteWorkCommand:
    authority: ClaimAuthority
    completed_at: str

@dataclass(frozen=True, slots=True)
class RetryWorkCommand:
    authority: ClaimAuthority
    failed_at: str
    decision: RetryDecision
    error: WorkError

@dataclass(frozen=True, slots=True)
class FailTerminalWorkCommand:
    authority: ClaimAuthority
    failed_at: str
    error: WorkError
```

Rules:

- `expected_revision` is non-negative and refers to the caller's latest
  successful claim or renewal;
- command timestamps are canonical UTC and supplied by the runtime clock;
- `lease_duration_seconds` must equal the accepted per-kind policy value;
- the runtime retry policy creates `RetryDecision` from the durable attempt
  count already present on the current claim;
- adapters validate that the decision agrees with the durable attempt count
  and configured policy version, but do not calculate exhaustion or backoff;
- a non-exhausted decision has `available_at > failed_at`;
- an exhausted decision has `available_at=None`;
- adapters reject policy disagreement rather than silently applying a
  different value.

The immutable retry decision is:

```python
@dataclass(frozen=True, slots=True)
class RetryDecision:
    policy_version: str
    maximum_attempts: int
    attempt_count: int
    exhausted: bool
    available_at: str | None
```

`exhausted` must equal `attempt_count >= maximum_attempts`. The attempt count
must match the current durable claim. This makes policy, rather than
persistence, the owner of exhaustion evaluation while allowing persistence to
reject an inconsistent command.

### WorkTransitionResult

```python
@dataclass(frozen=True, slots=True)
class WorkTransitionResult:
    work_item_id: ID
    kind: WorkItemKind
    from_status: WorkItemStatus
    to_status: WorkItemStatus
    occurred_at: str
    attempt_count: int
    revision: int
    available_at: str | None
    lease_expires_at: str | None
    error: WorkError | None
    exhausted: bool
```

The result reflects committed durable state.

- renewal has `running -> running`, a non-null lease expiry, no error, and
  `exhausted=False`;
- completion has `running -> completed`, no lease, no availability, and no
  error;
- scheduled retry has `running -> retrying`, a non-null future availability,
  no lease, a retryable error, and `exhausted=False`;
- terminal failure has `running -> dead_letter`, no lease or availability, a
  terminal error, and `exhausted=False`;
- exhausted retry has `running -> dead_letter`, no lease or availability, a
  retryable error, and `exhausted=True`.
- exhausted expired-work normalization has `running -> dead_letter`, no lease
  or availability, terminal category `attempts_exhausted`, and
  `exhausted=True`.

`WorkClaimOutcome` is the closed result union:

```python
WorkClaimOutcome: TypeAlias = WorkClaim | WorkTransitionResult
```

`WorkTransitionResult` is returned from claim selection only for the exhausted
expired-work normalization defined below.

## Exact Port Surface

The separate lifecycle protocol has exactly this public operation surface:

```python
class WorkItemLifecyclePort(Protocol):
    def claim_next(
        self,
        request: WorkClaimRequest,
    ) -> WorkClaimOutcome | None: ...

    def renew_lease(
        self,
        command: RenewLeaseCommand,
    ) -> WorkClaim: ...

    def complete(
        self,
        command: CompleteWorkCommand,
    ) -> WorkTransitionResult: ...

    def fail_retryable(
        self,
        command: RetryWorkCommand,
    ) -> WorkTransitionResult: ...

    def fail_terminal(
        self,
        command: FailTerminalWorkCommand,
    ) -> WorkTransitionResult: ...
```

There is no generic `update`, `set_status`, `release`, `delete`, `cancel`,
`replay`, `heartbeat`, batch-claim, list, or adapter transaction method.

`claim_next` returns `None` when no eligible item is claimable. A conditional
claim race that updates zero rows also returns `None`; it is not an operational
failure. It returns a `WorkTransitionResult` only when it dead-letters one
expired item whose attempt budget is exhausted. Other methods either return
committed state or raise a typed error.

## State and Transition Semantics

### Eligibility and ordering

A candidate is eligible when its kind is allowed and one of these is true at
the request's `claimed_at`:

- `pending` and `available_at <= claimed_at`;
- `retrying` and `available_at <= claimed_at`;
- `running` and `lease_expires_at <= claimed_at`.

Canonical ordering is:

1. expired `running` work before due `pending` or `retrying` work;
2. lower numeric `priority` before higher numeric `priority`;
3. earlier `available_at` for pending/retrying, or earlier
   `lease_expires_at` for expired running;
4. earlier `created_at`;
5. lexicographically smaller WorkItem ID.

This ordering is deterministic. It is not a fairness or latency guarantee.
The lower-number-is-higher direction matches the existing runtime queue's
`WorkItemPriority` convention; the lifecycle contract does not import or reuse
that legacy enum.

### Claim and reclaim

Claim/reclaim and selection are one atomic operation.

- `pending -> running` and `retrying -> running` create a fresh token, set the
  owner and finite lease, increment attempt exactly once, increment revision
  exactly once, clear `available_at` and prior failure metadata, and set
  `claimed_at`/`updated_at`;
- expired `running -> running` replaces owner and token, records the prior
  owner for the returned claim and structured event, increments attempt exactly
  once, and increments revision exactly once;
- a failed conditional mutation increments neither counter;
- a reclaimed worker's old authority is immediately stale;
- reclaim never reuses the prior token or extends the prior lease.
- owner, token, lease expiry, attempt count, revision, `claimed_at`, and
  `updated_at` are written in the same transaction;
- the returned `WorkClaim` contains those canonical committed values.

Claim/reclaim computes expiry from the policy for the selected kind:

```text
lease_expires_at = claimed_at + lease_duration_seconds
```

### Exhausted expired work

An expired `running` item with `attempt_count >= maximum_attempts` cannot
receive another execution grant. During `claim_next`, the adapter atomically
transitions the highest-ranked such candidate to `dead_letter`, clears lease
authority, records category `attempts_exhausted`, increments revision once,
does not increment attempt, and returns its committed `WorkTransitionResult`
with `exhausted=True`.

This normalization is one mutation transaction. The caller polls again to
select another item. It prevents both an attempt above the budget and a
permanently stranded expired row.

The maximum is read from the immutable policy in `WorkClaimRequest`.
Persistence applies that supplied policy to claim eligibility; it does not
invent a maximum or inspect handler exceptions.

### Renewal

Renewal is accepted only while:

```text
status == running
owner == authority.worker_id
token == authority.claim_token
revision == authority.expected_revision
renewed_at < current lease_expires_at
```

The new expiry is:

```text
max(current lease_expires_at, renewed_at + lease_duration_seconds)
```

It must be strictly later than the current expiry. A successful renewal
increments revision once, preserves attempt, owner, token, and status, and
returns a new `WorkClaim`. The caller must use its new revision.

This operation is a lease capability only. Periodic heartbeat behavior is not
part of this milestone.

### Completion

Completion requires valid, unexpired authority at `completed_at`. It clears all
lease fields, records `completed_at`, preserves attempt count, clears prior
failure metadata, and increments revision once.
Completion is never inferred from handler return values by persistence.

### Retryable failure and exhaustion

The runtime classifies and sanitizes the error. The immutable retry policy
evaluates exhaustion and computes `available_at` before the port is called.
Persistence does not classify exceptions, evaluate retry policy, generate
jitter, or calculate backoff.

With valid unexpired authority:

- if `RetryDecision.exhausted=False`, `fail_retryable` transitions
  `running -> retrying`, clears the lease, stores the sanitized error, sets the
  supplied future `available_at`, and increments revision once;
- if `RetryDecision.exhausted=True`, it transitions
  `running -> dead_letter`, clears the lease, stores the retryable error, sets
  `dead_lettered_at`, increments revision once, and returns
  `exhausted=True`.

Both transitions preserve the already-incremented attempt count from the
current claim. There is no intermediate retrying row or separate exhausted
state after exhaustion.

### Terminal failure

With valid unexpired authority, `fail_terminal` always transitions
`running -> dead_letter`, clears the lease, stores the sanitized terminal
error, sets `dead_lettered_at`, and increments revision once. Attempt count is
preserved. Intrinsically terminal failure and exhausted retryable failure are
distinguished by error retryability and `WorkTransitionResult.exhausted`.

### Terminal immutability

`completed` and `dead_letter` rows are immutable through this port.
Idempotently repeating a terminal operation is not reported as success; the
original authority has ended and the call raises `WorkClaimLostError`.

A future replay capability must create a new WorkItem with a new explicit
replay identity under a separately accepted decision.

## Durable State Invariants

All timestamps below are canonical UTC strings when present. Forbidden means
the durable value is null. `failure_metadata` means the bounded category and
sanitized message as one unit.

| State | `available_at` | `attempt_count` | `revision` | Lease owner/token/expiry | `claimed_at` | `completed_at` | `dead_lettered_at` | Failure metadata |
|---|---|---:|---:|---|---|---|---|---|
| `pending` | required | exactly 0 | exactly 0 | forbidden | forbidden | forbidden | forbidden | forbidden |
| `running` | forbidden | >= 1 | >= 1 | all required | required | forbidden | forbidden | forbidden |
| `retrying` | required and future at transition | >= 1 | >= 2 | all forbidden | required, retaining the latest claim time | forbidden | forbidden | required and retryable |
| `completed` | forbidden | >= 1 | >= 2 | all forbidden | required | required | forbidden | forbidden |
| `dead_letter` | forbidden | >= 1 | >= 2 | all forbidden | required | forbidden | required | required |

Additional invariants:

- lease owner, claim token, and lease expiry are either all present or all
  absent;
- running expiry is strictly later than its latest successful claim or renewal
  timestamp;
- retrying failure metadata is cleared by the next successful claim;
- completion clears any prior retry failure metadata;
- dead-letter failure metadata is retryable with `exhausted=True`, intrinsically
  terminal, or `attempts_exhausted` for expired-work normalization;
- `updated_at` equals the timestamp supplied for the latest successful
  lifecycle mutation;
- rejected, stale, conflicting, lost-race, and operationally failed operations
  change none of these values;
- no transition returns to `pending`.

Existing Phase 7.2 rows already satisfy the pending invariant:
`available_at` is present, `attempt_count` and lease/terminal columns do not yet
exist, and `revision=0`. Milestone 3.3 may add the missing columns with
lossless pending-compatible values; it must not reinterpret payloads,
identities, timestamps, priority, or availability.

## Clock Contract

Runtime owns a persistence-neutral clock:

```python
class UtcClock(Protocol):
    def now(self) -> str: ...
```

Every returned value must parse as timezone-aware ISO-8601 and normalize to
UTC. Production may use system UTC; tests inject a manual clock.

One operation samples the clock once. The same timestamp is passed in its
command and used for all eligibility, expiry, transition, and timestamp fields
in that atomic operation.

Adapters do not use SQLite date/time functions, local time, naive datetimes,
or a second wall-clock read to decide authority. Equality is expired:

```text
now >= lease_expires_at
```

No distributed clock-skew guarantee is claimed for the single-machine MVP.

## Frozen Lifecycle Policy Contract

The policy is immutable, explicitly constructed by composition, and passed to
claim commands. It is not stored per WorkItem in the MVP. This ADR freezes
required parameters and validation, not production numeric defaults; no
numeric values were authorized by RFC-001 or ADR-007 through ADR-009.

```python
@dataclass(frozen=True, slots=True)
class WorkKindPolicy:
    kind: WorkItemKind
    maximum_attempts: int
    lease_duration_seconds: int
    renewal_interval_seconds: int

@dataclass(frozen=True, slots=True)
class WorkLifecyclePolicy:
    policy_version: str
    kinds: tuple[WorkKindPolicy, ...]
    initial_retry_delay_seconds: int
    maximum_retry_delay_seconds: int
    backoff_multiplier_basis_points: int
    jitter_ratio_basis_points: int
```

Configuration validation is exact:

- `policy_version` is non-empty, at most 64 ASCII letters, digits, `.`, `_`,
  or `-`;
- `kinds` contains exactly one policy for each of the three frozen kinds;
- every integer is an actual integer, not `bool`;
- `maximum_attempts >= 1`;
- `lease_duration_seconds >= 1`;
- `1 <= renewal_interval_seconds < lease_duration_seconds`;
- `initial_retry_delay_seconds >= 1`;
- `maximum_retry_delay_seconds >= initial_retry_delay_seconds`;
- `backoff_multiplier_basis_points >= 10_000`;
- `0 <= jitter_ratio_basis_points < 10_000`.

The maximum attempt count is the configured maximum number of execution
grants, including the first claim and all reclaims. It is not a retry count.
Lease duration and attempt budget may differ by kind. Retry-delay parameters
are shared by the immutable policy version.

The policy is supplied rather than stored per row because attempts are durable
state while limits and timing are runtime policy. A policy change requires a
new version and governance review; one process may construct exactly one
policy version. Changing policy applies to all non-terminal rows after restart
and must be called out operationally before deployment.

### Retry delay formula

For durable `attempt_count = n`, configured initial delay `I`, maximum delay
`M`, multiplier basis points `B`, jitter basis points `J`, policy version `V`,
and WorkItem ID `W`, the policy uses integer arithmetic:

```text
uncapped_numerator = I * B ** (n - 1)
uncapped_denominator = 10_000 ** (n - 1)
uncapped = floor(uncapped_numerator / uncapped_denominator)
base = min(M, uncapped)
seed = SHA256(V + ":" + W + ":" + str(n))
d = unsigned_big_endian(seed[0:8])
jitter_offset = floor((2 * J * d) / (2**64 - 1)) - J
delay_seconds = max(1, min(M, floor(base * (10_000 + jitter_offset) / 10_000)))
available_at = failed_at + delay_seconds
```

The runtime retry-policy implementation owns this calculation. The formula is
deterministic across process restart and Python versions and provides
deterministic test behavior. It does not use process-random hash values,
mutable random state, the claim-token source, or randomness inside
persistence. `J=0` disables jitter.

For a validated provider `Retry-After` or equivalent bounded retry hint, the
runtime uses:

```text
delay_seconds = min(M, max(calculated_delay, ceil(retry_after_seconds)))
```

Negative, non-finite, malformed, or untrusted hints are ignored. Persistence
receives only the resulting `available_at`.

## Error Taxonomy and Outcome Classification

### WorkError

```python
@dataclass(frozen=True, slots=True)
class WorkError:
    category: WorkErrorCategory
    message: str
    retryable: bool
```

The category fixes retryability; callers cannot choose a contradictory boolean.

```python
class WorkErrorCategory(str, Enum):
    CONNECTOR_TRANSIENT = "connector_transient"
    RATE_LIMITED = "rate_limited"
    PERSISTENCE_OPERATIONAL = "persistence_operational"
    CHECKPOINT_CONFLICT = "checkpoint_conflict"
    DOWNSTREAM_TRANSIENT = "downstream_transient"
    UNEXPECTED = "unexpected"
    UNSUPPORTED_KIND = "unsupported_kind"
    PAYLOAD_INCOMPATIBLE = "payload_incompatible"
    PAYLOAD_INVALID = "payload_invalid"
    DEPENDENCY_MISSING = "dependency_missing"
    BINDING_MISMATCH = "binding_mismatch"
    AUTHORITATIVE_CONFLICT = "authoritative_conflict"
    HANDLER_CONTRACT_VIOLATION = "handler_contract_violation"
    DOMAIN_INVARIANT = "domain_invariant"
    ATTEMPTS_EXHAUSTED = "attempts_exhausted"
```

Retryable categories:

| Category | Meaning |
|---|---|
| `connector_transient` | timeout, reset, temporary DNS/transport failure |
| `rate_limited` | bounded provider throttling or service-unavailable response |
| `persistence_operational` | busy/locked or transient storage operational failure |
| `checkpoint_conflict` | stale checkpoint after reload/recollection is possible |
| `downstream_transient` | explicitly documented transient handler dependency |
| `unexpected` | unclassified exception, retried only within the finite budget |

Terminal categories:

| Category | Meaning |
|---|---|
| `unsupported_kind` | unknown WorkItem kind |
| `payload_incompatible` | unsupported payload schema/version |
| `payload_invalid` | malformed or invariant-breaking payload |
| `dependency_missing` | configured source, connector, or required handler absent |
| `binding_mismatch` | source/connector/checkpoint binding disagreement |
| `authoritative_conflict` | non-equivalent identity or durable output conflict |
| `handler_contract_violation` | handler violates its frozen input/output contract |
| `domain_invariant` | canonical domain invariant prevents execution |
| `attempts_exhausted` | expired last execution grant cannot be reclaimed |

`attempts_exhausted` is terminal and is written only by lifecycle exhaustion
normalization. A retryable handler error that exhausts the budget retains its
original category and is identified by `WorkTransitionResult.exhausted=True`.

Specific known exceptions are classified before broad exceptions. Process
termination signals, `KeyboardInterrupt`, and `SystemExit` are not converted
to WorkErrors; shutdown or lease expiry owns recovery.

### Message sanitization

Before a transition command is constructed, runtime must:

- convert the safe human-readable summary to one line;
- remove ASCII control characters;
- replace CR, LF, and tab with a single space;
- collapse repeated whitespace;
- bound the result to 1,024 Unicode code points;
- omit stack traces, exception representations containing arguments, payload
  bodies, provider responses, credentials, tokens, URIs with query strings,
  filesystem secrets, and claim tokens.

An empty safe message becomes the category value. Persistence validates these
bounds and rejects invalid input; it does not attempt secret detection.

## Contract Errors

The lifecycle error hierarchy extends the existing persistence-neutral
`PersistenceError`:

```text
PersistenceError
├── WorkLifecycleError
│   ├── WorkClaimLostError
│   ├── WorkInvalidTransitionError
│   ├── WorkLifecyclePolicyError
│   └── WorkLifecycleInvariantError
├── PayloadCompatibilityError            # existing
└── PersistenceOperationalError           # existing
```

- `WorkClaimLostError`: item missing, claim expired, or
  owner/token/revision authority mismatch. The error exposes only WorkItem ID
  and a stable reason code; it never exposes stored owner or token.
- `WorkInvalidTransitionError`: the item exists but the requested operation is
  not a legal transition from its durable lifecycle state, independent of
  whether the caller supplied a plausible authority tuple. This distinguishes
  invalid lifecycle use from stale or lost claim authority without exposing
  stored authority.
- `WorkLifecyclePolicyError`: command policy version/value disagrees with the
  adapter's configured accepted policy.
- `WorkLifecycleInvariantError`: durable state is internally inconsistent and
  cannot safely transition.
- existing `PayloadCompatibilityError`: selected kind or payload schema cannot
  be decoded.
- existing `PersistenceOperationalError`: storage operation failed without a
  safe committed lifecycle result.

DTO construction uses `TypeError` for wrong enum/DTO types and `ValueError` for
invalid values, matching the existing Phase 7 persistence convention.

After an operational error, callers must treat the outcome as uncertain, read
no authority into the exception, and rely on idempotent downstream writes plus
lease recovery. They do not blindly repeat a completion using stale revision.

## Structured Observability Contract

Milestone 3.2 requires structured lifecycle events but not a durable audit
table or a concrete logger. Runtime/scheduler observability later emits:

```text
work_claimed
work_reclaimed
work_lease_renewed
work_completed
work_retry_scheduled
work_dead_lettered
work_claim_lost
work_lifecycle_operational_error
```

Every event uses schema version `1` and includes, when applicable:

```text
event_name
event_schema_version
occurred_at
work_item_id
work_kind
from_status
to_status
worker_id
attempt_count
revision
policy_version
reclaimed
prior_worker_id
available_at
lease_expires_at
error_category
exhausted
```

Events must not include:

- claim tokens;
- WorkItem payloads or idempotency keys;
- raw documents, Evidence, Signals, or Research content;
- stack traces or unsanitized exception text;
- connector credentials or provider response bodies.

Successful events are emitted only from returned committed results. Claim-lost
events use the typed reason code. Operational-error events cannot assert a
destination state because commit outcome may be uncertain.

The durable WorkItem row remains the authoritative current state. Structured
events are operational observability and may be lost if a process crashes
after a database commit and before emission. A durable append-only transition
audit remains outside the MVP.

Execution remains at-least-once. Owner/token/revision checks prevent a stale
claimant from changing lifecycle state, but they cannot prove that downstream
domain writes did not commit before a crash or lease loss. Collection,
document-processing, and research replay safety must therefore use their
accepted deterministic identities, CAS, and future idempotent commit
boundaries; it cannot rely only on the lifecycle row.

## Compatibility Matrix

| Surface | Milestone 3.2 effect |
|---|---|
| Phase 7.1 WorkItem DTOs and schema version | unchanged |
| Phase 7.1 codecs, payload versions, kinds, and `IngestionWorkItem` union | reused unchanged |
| Phase 7.2 `WorkItemRepository.insert/get` | unchanged, pending-only |
| Phase 7.2 migration v0001 | unchanged |
| SQLite repositories/adapters | unchanged |
| `CollectionPersistencePort` | unchanged |
| `CollectionRunner` and `CollectionCoordinator` | unchanged |
| legacy `runtime.WorkItem` and queues | unchanged and not reused |
| `Store` and `InMemoryStore` | unchanged |
| Python support | 3.10 through 3.13 |

No lifecycle contract type is added to the `src.ingestion` namespace because
durable execution state is a persistence/runtime boundary, not part of the
frozen provider-neutral ingestion DTOs.

## Governance and Version Impact

This ADR adds no runtime behavior, serialized payload field, database column,
or migration. It therefore requires no project `SPEC_VERSION` bump by itself.

Acceptance freezes a new persistence-neutral contract for later
implementation. Any change after acceptance to:

- states or transition authority;
- public port signatures;
- DTO fields or invariant meanings;
- attempt/exhaustion semantics;
- policy values or retry formula;
- error retryability;

requires a new ADR and compatibility assessment. Adding a state, removing an
operation, or changing terminal semantics also requires RFC review because it
changes lifecycle invariants.

## Contract Test Specification

Acceptance requires a later executable contract implementation to prove:

1. enum values and exhaustive WorkItem-kind mapping;
2. exact protocol signatures and keyword/DTO boundaries;
3. DTO type, timestamp, counter, authority, and state invariants;
4. due pending/retrying claims and no claim before `available_at`;
5. expired-running reclaim and exclusion of unexpired running work;
6. deterministic priority, due/expiry, creation-time, and ID ordering;
7. two-claimant races with at most one canonical post-transition claim;
8. one attempt and one revision increment on successful claim/reclaim;
9. no attempt, revision, timestamp, or partial-field mutation after lost,
   rejected, stale, conflicting, or operationally failed operations;
10. owner, token, revision, status, and WorkItem-ID mismatch rejection;
11. renewal before expiry and stale renewal at the exact expiry instant;
12. renewal preserving owner/token/attempt and changing expiry/revision once;
13. completion fields, exact deltas, and stale completion rejection;
14. non-exhausted retry fields, exact deltas, and resolved availability;
15. intrinsic terminal failure fields and exact deltas;
16. exhausted retryable failure relative to the current claim's already
    incremented attempt count;
17. exhausted expired-work normalization without an extra attempt;
18. stale claimant rejection after a successful reclaim;
19. terminal immutability;
20. policy construction validation and policy disagreement failure;
21. deterministic retry calculations, maximum-delay cap, zero jitter, and
    provider-hint behavior;
22. UTC normalization, naive-time rejection, due equality, and expiry equality;
23. injected deterministic token-source behavior and fresh-token validation;
24. error-category retryability, sanitization, bounds, and secret/token
    exclusion;
25. canonical returned DTO values matching committed durable state;
26. structured event field allowlist and claim-token prohibition;
27. absence of SQLite/runtime/Store imports or infrastructure types from
    contract modules;
28. compatibility with all three frozen Phase 7.1 payloads and v0001 pending
    rows;
29. adapter restart expectations for durable non-terminal and terminal state;
30. adapter concurrency expectations for claim/reclaim authority;
31. Python 3.10 through 3.13 behavior.

These are adapter-neutral contract gates. SQLite race, rollback, migration, and
restart tests belong to Milestones 3.3 and 3.4.

## Alternatives Considered

### Store maximum attempts on every WorkItem

Not selected for the MVP. It would require a creation-path policy field and
would couple the frozen pending insertion contract to runtime timing policy.
Durable attempt count plus one explicitly versioned process policy is smaller.

### Let persistence calculate backoff and classify exceptions

Rejected. Persistence cannot interpret provider or handler failures without
reversing the accepted ownership boundary. Runtime supplies a classified,
sanitized error and an exact future availability.

### Use random jitter on every retry

Rejected. Mutable random state makes restart behavior and tests
non-reproducible. Stable SHA-256-derived jitter spreads retries while remaining
deterministic.

### Permit reclaim above the attempt budget

Rejected. That makes “maximum attempts” untrue and permits crash loops to run
forever. Expired work at budget is dead-lettered without another grant.

### Treat an expired last attempt as permanently running

Rejected. It creates an unrecoverable durable lock. Exhaustion normalization
provides a terminal destination.

### Make terminal operations idempotent success

Rejected. A repeated completion may be a stale worker after reclaim. Reporting
success would weaken owner/token/revision authority and conceal concurrency
errors.

### Add cancellation, replay, generic transition, or batch claim

Rejected for Phase 7.3 MVP. Each expands lifecycle authority and needs
separate requirements and governance.

### Add a durable lifecycle audit table

Not required for the MVP by ADR-009. Current durable state plus bounded
structured operational events satisfies this milestone's observability
boundary.

## Consequences

### Positive

- later schema and adapter work has one exact, persistence-neutral target;
- attempt exhaustion cannot create a sixth state or a permanently running row;
- stale workers cannot convert uncertain at-least-once execution into false
  lifecycle success;
- retry timing is finite, deterministic, and restart-stable;
- policy and exception classification remain outside persistence;
- existing ingestion, persistence, runtime compatibility, and Store contracts
  remain frozen.

### Negative

- all non-terminal work uses one process policy version after restart;
- deterministic jitter is more specified than a simple exponential delay;
- claim polling must repeat after it normalizes one exhausted expired row;
- operational events are not guaranteed durable across a post-commit crash;
- long-running handlers will eventually need scheduler-owned renewal behavior,
  which remains unimplemented.

## Acceptance Gates

The project owner accepted:

1. the exact DTOs and five-method port surface;
2. explicit ISO-8601 UTC command timestamps and strict expiry equality;
3. configurable, validated per-kind lease, renewal, and attempt policy without
   invented production numeric defaults;
4. runtime-supplied versioned policy rather than per-row maximum attempts;
5. deterministic SHA-256 retry jitter and provider-hint rule;
6. exhaustion during retry failure and expired-work normalization;
7. the error taxonomy, sanitization boundary, and retryability table;
8. structured non-durable observability without claim tokens or payloads;
9. terminal immutability and exclusion of replay/cancellation;
10. the compatibility and contract-test matrices.

Closure state:

```text
ADR-010: Accepted
Milestone 3.2 governance review: Complete
Lifecycle SQL/migration: Not implemented
Lifecycle adapter: Not implemented
Worker/scheduler behavior: Not implemented
```

## References

- [RFC-001: Durable Ingestion and Research Triggering](../RFC/RFC-001-durable-ingestion-research-triggering.md)
- [ADR-007: Phase 7 Foundation Decisions](ADR-007-phase7-foundation-decisions.md)
- [ADR-008: Phase 7 Persistence Decisions](ADR-008-phase7-persistence-decisions.md)
- [ADR-009: Phase 7 Runtime Composition and WorkItem Worker Boundary](ADR-009-phase7-runtime-composition-and-worker-boundary.md)
- [Phase 7.1 WorkItem DTOs](../src/ingestion/work.py)
- [Phase 7.2 persistence models](../src/persistence/ingestion/models.py)
- [Phase 7.2 persistence ports](../src/persistence/ingestion/ports.py)
- [Phase 7.2 persistence errors](../src/persistence/ingestion/errors.py)
- [Governance](../GOVERNANCE.md)
- [Specification Versioning](../SPEC_VERSION.md)
- [Schema Evolution](../SCHEMA_EVOLUTION.md)
