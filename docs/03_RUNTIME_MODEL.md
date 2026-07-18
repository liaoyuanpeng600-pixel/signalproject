# Runtime Model

> **Document role:** Defines runtime responsibilities for executing the Workflow Model. Specifies components, execution lifecycle, stage specifications, error recovery, and audit logging. Sits between the Workflow Model and the Implementation layer.
>
> This document does not redefine the workflow. It executes the workflow. Runtime boundary is explicit.
>
> Read alongside: [00_ARCHITECTURE_PRINCIPLES.md](00_ARCHITECTURE_PRINCIPLES.md) (frozen), [01_OBJECT_MODEL.md](01_OBJECT_MODEL.md) (frozen), [02_WORKFLOW_MODEL.md](02_WORKFLOW_MODEL.md) (frozen).

---

## Document Metadata

| Field | Value |
|---|---|
| **Status** | Draft for review |
| **Version** | 1.0 |
| **Effective Date** | TBD on Workflow freeze |
| **Next Review** | TBD |
| **Owner** | Runtime |

> **Note.** Runtime executes the workflow as defined. It does not redefine stages, gates, cardinalities, or failure paths. Any change to workflow behavior must be proposed through the Workflow Model amendment process.

---

## Purpose

The Runtime Model defines **how the Workflow Model is executed**.

It answers four questions:

- **What components execute the workflow?** — the runtime components and their responsibilities.
- **What happens during a cycle?** — the execution lifecycle.
- **How are Workflow gates evaluated?** — the per-stage execution specification.
- **How does Runtime recover from failures?** — the error recovery flow.

This document is implementation-independent. It does not specify technologies (databases, queues, schedulers). It specifies **roles** and **responsibilities**. Implementation choices belong in the Implementation layer.

---

## Hierarchy Position

```
Architecture Principles   ← constitutional root (frozen)
        ↓
Object Model             ← frozen v1.0
        ↓
Workflow Model           ← frozen v1.0
        ↓
Constitutions            ← domain-level constitutional documents
        ↓
Runtime Model            ← this document
        ↓
Implementation
```

The Runtime Model is **above** Implementation and **below** Constitutions. Constitutions may refine the runtime for their domain (e.g., specifying curator intervention points) but may not contradict it.

---

## Principles Applied

This document conforms to the [Architecture Principles](00_ARCHITECTURE_PRINCIPLES.md) and respects the [Object Model](01_OBJECT_MODEL.md) and [Workflow Model](02_WORKFLOW_MODEL.md):

- **P1 — Reality First**: Runtime executes the workflow as defined; it does not abstract reality.
- **P2 — Evidence First**: Every Stage 2 (Evidence Production) gate is evaluated before persistence; Evidence quality is preserved.
- **P3 — Evolution First**: Runtime supports re-examination and re-evaluation of Objects across cycles.
- **P4 — Knowledge Accumulation**: Runtime persists all Objects per Object Model lifecycle; nothing is consumed.
- **P5 — Traceability**: Every Runtime transition logs the gate evaluations and decisions that produced the result.
- **P6 — Research Before Decision**: Runtime produces research artifacts; it does not produce decisions.
- **P7 — Human Judgment**: Runtime surfaces human intervention points; it does not replace human judgment.
- **P8 — Composable Objects**: Runtime components are loosely coupled; failure in one does not invalidate others.
- **P9 — Evolution over Prediction**: Runtime optimizes for understanding accumulation, not throughput.
- **P10 — Incremental Evolution**: Runtime extensions (new components) are added, not replacements.

---

## Runtime Boundary

Runtime **executes** the Workflow Model as defined. It **must not**:

- **Redefine workflow logic.** Stages, gates, cardinalities, and failure paths are fixed by the Workflow Model.
- **Introduce new stages.** New stages require a Workflow Model amendment.
- **Skip gates.** Every gate defined in the Workflow Model must be evaluated.
- **Change failure paths.** Where an Object goes on failure is fixed by the Workflow Model.
- **Override Object Model rules.** Object lifecycle, immutability, and preservation rules are fixed.
- **Override Architecture Principles.** The runtime may not implement behavior that violates P1–P10.

Runtime **is responsible for**:

- **Executing** the gates defined in the Workflow Model, in order.
- **Evaluating** each gate against the current Object and context.
- **Routing** Objects to their failure-path destination on gate failure.
- **Persisting** Objects per the Object Model's lifecycle rules.
- **Retrying** per the Workflow Model's retry paths.
- **Logging** every transition, gate evaluation, and decision.
- **Emitting** observations per Object Model operational concepts.

---

## Runtime Components

Seven runtime components. Each has a single, well-defined responsibility.

### 1. Scheduler

**Responsibility.** Triggers workflow cycles per the Workflow Model's trigger definitions.

**Inputs.**
- Cycle schedule (e.g., scheduled intervals per workflow)
- Burst triggers (e.g., breaking-news detection)
- Manual trigger requests
- Replay trigger requests

**Outputs.**
- Cycle initiation events to the Queue

**Constraints.**
- Scheduler does not decide *whether* to trigger a cycle; the workflow trigger policy is fixed.
- Scheduler emits trigger events; it does not execute stages.

### 2. Queue

**Responsibility.** Holds work items awaiting execution, per stage.

**Inputs.**
- Cycle initiation events from Scheduler
- Stage outputs from previous stage (for chained execution)
- Retry work items from Retry Manager

**Outputs.**
- Work items to Executor

**Constraints.**
- Queue has bounded capacity with defined overflow behavior.
- Queue ordering respects priority (per Constitution tier policy).
- Queue does not decide execution; it holds items.

### 3. Executor

**Responsibility.** Runs each workflow stage's logic.

**Inputs.**
- Work items from Queue
- Objects from Persistence (for stage inputs)

**Outputs.**
- Stage results (Object produced, or failure-path destination)
- Stage execution events to Validator

**Constraints.**
- Executor invokes stage logic per Workflow Model stage definitions.
- Executor does not decide gate pass/fail; it forwards results to Validator.
- Executor is the only component that mutates Object state.

### 4. Validator

**Responsibility.** Evaluates each gate against the current Object and context.

**Inputs.**
- Stage result from Executor
- Gate definitions from Workflow Model (23 gates total)

**Outputs.**
- Gate evaluation results (pass/fail per gate)
- Routing instructions: advance, reject, hold, or pending

**Constraints.**
- Validator does not modify Objects.
- Validator does not decide retry; it forwards to Retry Manager.
- Validator emits evaluations to Audit Logger.

### 5. Persistence

**Responsibility.** Stores Objects per Object Model lifecycle rules.

**Inputs.**
- Objects to persist (from Executor after gate pass)
- Lifecycle state changes (from Executor after gate pass or rejection)

**Outputs.**
- Persisted Objects (queryable)
- Persistence checkpoint events to Audit Logger

**Constraints.**
- Evidence is immutable once persisted.
- OverrideRecord is append-only.
- Lifecycle transitions follow the Workflow Model.
- Persistence does not decide lifecycle; it stores decisions made by Executor/Validator.

### 6. Retry Manager

**Responsibility.** Implements retry strategies per the Workflow Model's retry paths.

**Inputs.**
- Failed work items from Validator (with retry-path information)
- Retry eligibility (per gate; 23 retry triggers)

**Outputs.**
- Retry work items to Queue
- Dead-letter items (when retry exhausted or non-retryable)

**Constraints.**
- Retry Manager applies the Workflow Model's retry paths; it does not invent new ones.
- Retry Manager respects gate-specific retry triggers.
- Retry Manager emits retry events to Audit Logger.

### 7. Audit Logger

**Responsibility.** Records every Runtime event for traceability and observability.

**Inputs.**
- All events from all other components (Scheduler, Executor, Validator, Persistence, Retry Manager)

**Outputs.**
- Audit log entries (immutable, append-only)
- CycleReport per cycle (per Object Model operational concepts)
- FailureReport per failure event

**Constraints.**
- Audit log is immutable.
- Every gate evaluation is logged.
- Every state transition is logged.
- Every retry attempt is logged.
- Audit Logger does not make decisions; it records them.

---

## Runtime Architecture Diagram

The components and their relationships:

```
                       ┌─────────────────┐
                       │   Scheduler     │
                       │  (triggers)     │
                       └────────┬────────┘
                                │ cycle trigger
                                ▼
   ┌──────────┐    ┌─────────────────────────┐    ┌─────────────┐
   │  Queue   │◄──►│        Executor         │───►│ Persistence │
   │  (holds) │    │  (runs stage logic)     │    │  (stores)   │
   └────┬─────┘    └────────────┬────────────┘    └──────┬──────┘
        │                       │                       │
        │ retry                 │ result                │ lifecycle
        │                       ▼                       │
        │              ┌─────────────────┐              │
        │              │    Validator    │              │
        │              │ (evaluates gates)│              │
        │              └────────┬────────┘              │
        │                       │                       │
        │                       │ evaluation             │
        │                       ▼                       │
        │              ┌─────────────────┐              │
        └─────────────►│    Retry Mgr    │◄─────────────┘
                       │  (retry policy) │
                       └────────┬────────┘
                                │
                                │ all events
                                ▼
                       ┌─────────────────┐
                       │   Audit Logger   │
                       │  (records all)   │
                       └─────────────────┘
```

**Data flow:**

1. Scheduler emits trigger events to Queue.
2. Queue holds work items; releases them to Executor.
3. Executor runs stage logic; invokes Validator for gate evaluation.
4. Validator returns pass/fail per gate.
5. On all-gates-pass: Executor sends Objects to Persistence; next-stage item to Queue.
6. On gate-fail: Executor sends to Retry Manager (if retryable) or to failure-path destination.
7. Retry Manager schedules retry; on exhaustion, sends to dead-letter.
8. All components emit events to Audit Logger.

---

## Execution Lifecycle

A single workflow cycle follows this lifecycle:

```
   ┌────────────────┐
   │ Cycle Trigger  │  Scheduler emits
   └───────┬────────┘
           │
           ▼
   ┌────────────────┐
   │ Stage 1 Run    │  Source Observation
   │ + Validate     │  Gates S1-G1, S1-G2, S1-G3
   └───────┬────────┘
           │ all pass
           ▼
   ┌────────────────┐
   │ Persist        │  Source health logged
   │ (partial)      │
   └───────┬────────┘
           │
           ▼
   ┌────────────────┐
   │ Stage 2 Run    │  Evidence Production
   │ + Validate     │  Gates S2-G1, S2-G2, S2-G3, S2-G4
   └───────┬────────┘
           │ all pass
           ▼
   ┌────────────────┐
   │ Persist        │  Evidence persisted (immutable)
   │ (Evidence)     │
   └───────┬────────┘
           │
           ▼
   ┌────────────────┐
   │ Stage 3 Run    │  Signal Extraction
   │ + Validate     │  Gates S3-G1, S3-G3, S3-G4
   └───────┬────────┘
           │ all pass
           ▼
   ┌────────────────┐
   │ Persist        │  Signal persisted
   │ (Signal)       │
   └───────┬────────┘
           │
           ▼
   ┌────────────────┐
   │ Stage 4 Run    │  Research Synthesis
   │ + Validate     │  Gates S4-G1, S4-G2, S4-G3, S4-G4
   └───────┬────────┘
           │ all pass
           ▼
   ┌────────────────┐
   │ Persist        │  Research persisted
   │ (Research)     │
   └───────┬────────┘
           │
           ▼
   ┌────────────────┐
   │ Stage 5 Run    │  Thesis Update
   │ + Validate     │  Gates S5-G1, S5-G2, S5-G3
   └───────┬────────┘
           │ all pass
           ▼
   ┌────────────────┐
   │ Persist        │  Thesis (new/updated) persisted
   │ (Thesis)       │
   └───────┬────────┘
           │
           ▼
   ┌────────────────┐
   │ Stage 6 Run    │  Knowledge Update
   │ + Validate     │  Gates S6-G1, S6-G2, S6-G3
   └───────┬────────┘
           │ all pass
           ▼
   ┌────────────────┐
   │ Persist        │  Knowledge integrated
   │ (Knowledge)    │
   └───────┬────────┘
           │
           ▼
   ┌────────────────┐
   │ CycleReport    │  Audit Logger emits
   │ emitted        │
   └────────────────┘
```

**Cycle atomicity.** A cycle is sequential. A cycle runs to completion (or cycle-level abort) before the next cycle begins, by default.

---

## Per-Stage Specification

Each stage's runtime specification. The stage logic itself is per the Workflow Model; this document specifies *how* Runtime executes it.

### Stage 1 — Source Observation

| Facet | Specification |
|---|---|
| **Executor** | Source Executor |
| **Trigger** | Cycle initiation from Scheduler |
| **Input** | Source registry, active Source list |
| **Output** | Candidate observations (zero or more); Source health updates |
| **Retry strategy** | S1-G1: next scheduled cycle. S1-G2: manual fix. S1-G3: manual review. |
| **Failure handling** | S1-G1: Source marked `degraded`; cycle skips Source. S1-G2: cycle logs; Source skipped. S1-G3: candidate flagged `timestamp_anomaly`. |
| **Logging** | Per-Source reachability result; per-candidate timestamp check; Source health updates |
| **Persistence checkpoint** | Source health updates persisted; no candidate persistence until Stage 2 |

### Stage 2 — Evidence Production

| Facet | Specification |
|---|---|
| **Executor** | Evidence Producer |
| **Trigger** | Stage 1 success for one or more candidates |
| **Input** | Candidate observations, Source |
| **Output** | Evidence objects (zero or one per candidate) |
| **Retry strategy** | S2-G1: manual attribution. S2-G2: after investigation. S2-G3: manual completion. S2-G4: manual retrieval fix. |
| **Failure handling** | S2-G1/G2/G3: candidate rejected, logged. S2-G4: Evidence marked `non_retrievable`, retained. |
| **Logging** | Source attribution, content preservation result, quality metadata, retrievability status |
| **Persistence checkpoint** | Evidence persisted on gate pass (immutable); `non_retrievable` Evidence also persisted with status flag |

### Stage 3 — Signal Extraction

| Facet | Specification |
|---|---|
| **Executor** | Signal Extractor |
| **Trigger** | Stage 2 success (Evidence produced) |
| **Input** | Evidence, Entity reference |
| **Output** | Signal objects (zero or more per Evidence); Entity resolution results |
| **Retry strategy** | S3-G1: when Entity master updated. S3-G3: with refined Evidence. S3-G4: with improved event-detection criteria. |
| **Failure handling** | All S3 failures: Evidence retained, no Signal produced. Evidence remains available for re-examination. |
| **Logging** | Entity resolution result, falsifiability check, distinct-event check |
| **Persistence checkpoint** | Signal persisted on gate pass; failed Evidence remains in Persistence unchanged |

### Stage 4 — Research Synthesis

| Facet | Specification |
|---|---|
| **Executor** | Research Synthesizer |
| **Trigger** | Stage 3 success (Signals available) |
| **Input** | Signals, Entity, research question |
| **Output** | Research object (zero or one per investigation) |
| **Retry strategy** | S4-G1: when question clarified. S4-G2: when more Signals arrive. S4-G3: when context available. S4-G4: manual trace completion. |
| **Failure handling** | S4-G1/G2: Signals retained, no Research. S4-G3: Signals retained, Research held. S4-G4: Research produced but flagged `traceability_gaps`. |
| **Logging** | Question coherence result, signal sufficiency, entity context, traceability status |
| **Persistence checkpoint** | Research persisted on gate pass; held Research tracked for retry; flagged Research persisted with status |

### Stage 5 — Thesis Update

| Facet | Specification |
|---|---|
| **Executor** | Thesis Updater |
| **Trigger** | Stage 4 success (Research available) |
| **Input** | Research (new), existing Thesis (optional, per same Entity) |
| **Output** | Thesis (new, evolved, or supersession pair) |
| **Retry strategy** | S5-G1: when interpretation clarified. S5-G2: when refutation criteria added. S5-G3: when Entity added to master. |
| **Failure handling** | S5-G1/G2: Research retained, no Thesis. S5-G3: Research retained, Thesis held. Superseded Thesis preserved with full history. |
| **Logging** | Path decision (Evolve/Supersede/Hold), interpretation coherence, falsifiability, entity recognition, state transition |
| **Persistence checkpoint** | Thesis persisted on gate pass; supersession pair persisted (predecessor marked, successor created) |

### Stage 6 — Knowledge Update

| Facet | Specification |
|---|---|
| **Executor** | Knowledge Updater |
| **Trigger** | Stage 5 success (Thesis available) |
| **Input** | Thesis, existing Knowledge |
| **Output** | Knowledge update (cumulative) |
| **Retry strategy** | S6-G1: when Thesis matures. S6-G2: when links restored. S6-G3: when structure repaired. |
| **Failure handling** | All S6 failures: Thesis recorded with `pending_integration` status; existing Knowledge unchanged. |
| **Logging** | Maturity check, traceability preservation, structure consistency check, integration timestamp |
| **Persistence checkpoint** | Knowledge updated on gate pass; pending Thesis tracked for future integration |

---

## Error Recovery Flow

The Runtime's error recovery flow follows the Workflow Model's failure paths and retry strategies.

```
                          ┌──────────────────────┐
                          │  Stage execution     │
                          │  (Executor)          │
                          └──────────┬───────────┘
                                     │
                                     ▼
                          ┌──────────────────────┐
                          │  Gate evaluation     │
                          │  (Validator)         │
                          └──────────┬───────────┘
                                     │
                       ┌─────────────┴─────────────┐
                       │                           │
                   all pass                    any fail
                       │                           │
                       ▼                           ▼
            ┌─────────────────────┐    ┌────────────────────────┐
            │ Persist Object      │    │  Is gate retryable?     │
            │ (Persistence)       │    │  (per Workflow Model)  │
            └──────────┬──────────┘    └────────────┬───────────┘
                       │                           │
                       │                  ┌────────┴────────┐
                       │                  │                 │
                       │              retryable        non-retryable
                       │                  │                 │
                       │                  ▼                 ▼
                       │    ┌─────────────────────┐  ┌──────────────────────┐
                       │    │   Retry Manager     │  │  Route to failure    │
                       │    │   (retry eligible)  │  │  path destination    │
                       │    └──────────┬──────────┘  └──────────┬───────────┘
                       │               │                         │
                       │               ▼                         ▼
                       │    ┌─────────────────────┐  ┌──────────────────────┐
                       │    │  Wait for retry     │  │  Reject / Hold /      │
                       │    │  trigger             │  │  Pending / Degraded   │
                       │    └──────────┬──────────┘  └──────────┬───────────┘
                       │               │                         │
                       │               ▼                         ▼
                       │    ┌─────────────────────┐  ┌──────────────────────┐
                       │    │  Re-enter stage      │  │  Object persisted    │
                       │    │  (retry)             │  │  with status change   │
                       │    └──────────┬──────────┘  └──────────────────────┘
                       │               │
                       └───────────────┴─────► to next stage
```

### Recovery Rules

1. **All gate failures are logged.** Every failure is recorded in the Audit Logger.
2. **Retry triggers come from the Workflow Model.** Retry Manager does not invent new triggers.
3. **Failed Objects are persisted with status change.** Per Object Model lifecycle, nothing is deleted.
4. **Dead-letter items are reviewed.** Items that exhaust retry are flagged for human review (via Reports layer).
5. **Cycle-level failures abort the cycle.** If a critical infrastructure failure occurs (e.g., Persistence unavailable), the cycle aborts cleanly.

---

## Audit Logging

The Audit Logger records every Runtime event. The log is immutable and append-only.

### Logged Events

| Event Category | Events Logged |
|---|---|
| **Cycle** | Cycle start, cycle end, cycle abort |
| **Stage** | Stage start, stage end, stage abort |
| **Gate** | Gate evaluation per gate (pass/fail, reason) |
| **Object** | Object creation, Object state transition, Object lifecycle change |
| **Retry** | Retry attempt, retry success, retry exhausted |
| **Failure** | Failure destination, failure reason |
| **Conflict** | Conflict detected (per Rule 3), conflict surfacing |
| **Concurrency** | Concurrent update attempt, serialization event |

### Log Entry Structure

Each log entry contains:

- Timestamp
- Cycle ID
- Workflow version
- Stage ID
- Object ID (if applicable)
- Gate ID (if applicable)
- Event type
- Result (pass/fail/retry/dead-letter)
- Reason (if failure)

### Observability Outputs

Beyond the log, the Audit Logger emits:

- **CycleReport** (per Object Model operational concepts): per-cycle summary.
- **FailureReport**: aggregated failure metrics per cycle.
- **CalibrationData**: outcomes used for downstream calibration (per Object Model Rule 4).

---

## Resolved Open Questions (from Workflow Model)

The following Workflow Model Open Questions are resolved by the Runtime Model:

### OQ-4 — Batch vs. Streaming

**Resolution (Runtime).** Runtime supports both:

- **Default mode: Batch.** Cycles are deterministic; all stages within a cycle run to completion before the next cycle begins.
- **Burst mode: Streaming.** Lower-latency mode for breaking-news triggers; signals flow through stages as soon as they're produced.
- **Replay mode: Deterministic Batch.** With pinned versions; used for audit and backtesting.

### OQ-6 — Thesis Maturity Trigger

**Resolution (Runtime).** Runtime evaluates maturity criteria but does not define them.

- Runtime emits maturity metrics based on configurable thresholds (time-stable, revision-stable, etc.).
- Maturity criteria are defined by Constitution (out of Runtime scope).
- Runtime applies the criteria at Stage 6; if a Thesis meets criteria, it proceeds to integration.

### OQ-7 — Conflict Surfacing

**Resolution (Runtime).** Runtime emits conflict events; surfacing cadence is a Reporting concern.

- Stage 5 emits "conflict detected" events for all Path B (Supersede) outcomes.
- Runtime does not decide when humans see conflicts; that is a Reports-layer concern.

### OQ-8 — Concurrent Thesis Updates

**Resolution (Runtime).** Runtime serializes Thesis updates per Thesis.

- Per-Thesis serialization: only one update in progress per Thesis at a time.
- If a second update arrives while one is in progress, the second is queued.
- Optimistic concurrency for non-Thesis updates (Signals, Research) is acceptable.
- All concurrent attempts are logged.

### OQ-9 — Conflicting Source Evidence

**Resolution (Runtime).** Runtime applies source priority rules; all variants are retained.

- Source priority is configurable (per Constitution or default: most recent).
- All Evidence variants are persisted (per Object Model preservation rule).
- The conflict is recorded as a relationship between Evidence objects.
- Downstream stages resolve at the Signal level (which Evidence grounds which Signal).

### OQ-10 — Retroactive Corrections

**Resolution (Runtime).** Runtime emits correction Signals; existing Objects are flagged, not auto-updated.

- A new Evidence from a corrected Source produces a "correction Signal."
- The correction Signal is grounded by the new Evidence and references the prior Signal(s).
- Prior Signal, Research, Thesis are flagged for re-examination (via metadata), not auto-modified.
- Human/curator review (via Reports) decides whether to revise downstream Objects.

### OQ-11 — `non_retrievable` Evidence Lifecycle

**Resolution (Runtime).** Runtime retains `non_retrievable` Evidence per Object Model lifecycle.

- Evidence is persisted with `non_retrievable` status flag.
- Excluded from Signal grounding (Stage 3).
- Periodic re-check against Source may upgrade status if retrieval succeeds.
- Never deleted.

### OQ-12 — Reject vs. Delete Semantics

**Resolution (Runtime).** Reject = status change for Objects; discard for raw candidates.

- For Objects (Evidence, Signal, Research, Thesis): Reject sets the Object's status to a reject-related state; the Object remains in Persistence.
- For raw candidates (pre-Evidence, Stage 1–2): Reject discards the raw data; not an Object.
- Confirmed: nothing in the system is deleted except raw candidate data.

### Remaining Open Questions

The following Workflow Model Open Questions remain unresolved by the Runtime Model (they are constitutional or design concerns, not runtime):

- **OQ-1**: Thesis Update Path decision logic (Evolve/Supersede/Hold) — requires Constitution definition.
- **OQ-2**: Timing and ordering constraints — requires Workflow Model clarification.
- **OQ-3**: Reverse edges and re-examination — requires Workflow Model design.
- **OQ-5**: Macro-level Signal entry point — requires Object Model clarification.

---

## Remaining Implementation Questions

These are questions that block Implementation but not Runtime Model freeze. They concern technology choices that the Runtime Model deliberately leaves open.

### OQ-Imp-1 — Cycle Orchestration Mechanism

How are stages chained within a cycle? Synchronous execution, message-driven chaining, or state machine?

**Implications.** Affects latency, throughput, and failure isolation.

### OQ-Imp-2 — Queue Implementation

Is the Queue a single FIFO queue, per-stage queue, or priority queue with tier-based ordering?

**Implications.** Affects latency for high-tier entities (Watchlist Tier 1) and backpressure handling.

### OQ-Imp-3 — Persistence Strategy

How are Objects persisted? Event-sourced log, relational store, hybrid?

**Implications.** Affects query performance, audit completeness, and Evidence immutability guarantees.

### OQ-Imp-4 — Retry Mechanism

How is retry implemented? In-memory delay, scheduled re-execution, or dead-letter queue?

**Implications.** Affects retry behavior under failure and recovery time.

### OQ-Imp-5 — Audit Log Destination

Where is the Audit Log persisted? Same store as Objects, separate append-only log, or external system?

**Implications.** Affects audit integrity, query performance, and operational visibility.

### OQ-Imp-6 — Validator Implementation

How are gates evaluated? Rule engine, programmatic checks, or hybrid?

**Implications.** Affects gate extensibility and Runtime customization.

### OQ-Imp-7 — CycleReport Emission

When is CycleReport emitted? End of cycle only, or real-time per stage?

**Implications.** Affects observability latency and Report freshness.

### OQ-Imp-8 — Concurrency Model

How are concurrent cycles handled? Single-writer serialization, optimistic concurrency, or CRDTs?

**Implications.** Affects throughput and conflict probability.

---

## Version History

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-07-18 | Initial Runtime Model v1.0 draft for review; resolves 8 Workflow Open Questions; introduces 8 Implementation Open Questions |
