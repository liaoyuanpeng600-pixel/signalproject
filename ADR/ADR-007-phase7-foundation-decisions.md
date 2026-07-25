# ADR-007: Phase 7 Foundation Decisions

> **Status:** accepted
> **Date:** 2026-07-25
> **Supersedes:** None
> **Superseded by:** None

## Context

Signal Project v0.1.0 provides first-class `Source`, `Evidence`, `Signal`,
`Research`, and `Thesis` objects, a six-stage workflow, in-memory persistence
and runtime components, research services, and deterministic reports. It does
not yet form a continuous operating loop from external information to durable
research work.

Phase 7 needs:

- an external-source boundary that prevents provider APIs from entering the
  core and research layers;
- incremental collection with provenance and deterministic deduplication;
- durable processing that can resume after interruption;
- deterministic research triggering that preserves the existing
  Signal → Research → Thesis lineage.

RFC-001 evaluated the required foundation, alternatives, transaction
boundaries, migration approach, and seven open questions. This ADR records the
foundation decisions accepted at the RFC-001 decision freeze. It does not
implement them or change an existing schema.

## Decisions

### 1. Architecture

Phase 7 uses a **modular monolith with durable staged work**. The canonical
flow remains Evidence-first:

```text
External Source
  → Connector
  → RawDocument
  → Evidence
  → Signal
  → ResearchWorkItem
  → Research
  → Thesis
  → Existing Reports
```

Provider isolation and a deterministic control plane are mandatory. Scheduler,
checkpoint, idempotency, retry, lease, and lifecycle behavior remain ordinary
application/runtime code rather than agent decisions.

### 2. Durable persistence

SQLite is the Phase 7.2 MVP durable persistence backend.

Constraints:

- Phase 7.1 does not implement a database.
- Persistence access remains behind repository boundaries.
- The current Store remains a compatibility facade during migration.
- The logical schema avoids unnecessary SQLite-specific coupling and preserves
  a later PostgreSQL migration path.

### 3. Initial connectors

The two Phase 7 MVP connectors are:

1. RSS Connector.
2. Deterministic Filing Fixture Connector.

The fixture connector validates document identity, revisions, provenance,
larger documents, cursor behavior, and failures without live network
dependency. Phase 7.1 does not implement a live SEC connector, and required
tests do not depend on live Internet access.

### 4. WorkItem model

Phase 7 uses typed WorkItems as the cross-stage task abstraction. It does not
introduce a first-class `ResearchRequest` domain aggregate.

Initial work kinds are:

```text
CollectionWorkItem
DocumentProcessingWorkItem
ResearchWorkItem
```

Each kind has a typed and versioned payload. Durable status, lease, retry,
idempotency, and dead-letter behavior are Phase 7.2 concerns, not Phase 7.1
implementation work.

### 5. Evidence correction

The final Evidence correction schema is deferred with a recorded direction:

- Phase 7.1 does not modify the existing Evidence schema.
- Original Evidence must never be overwritten.
- A future `EvidenceRevision` object or append-only revision relation should
  retain the full correction history.
- The final schema requires a separate RFC or ADR and schema-version review.

### 6. Human Signal review

A mandatory human Signal review gate is deferred. Phase 7 MVP Signal promotion
uses:

- Evidence grounding;
- confidence;
- importance;
- deterministic policy.

A future review gate must be justified by operational results. This decision
does not prohibit a persisted hold outcome or curator override.

### 7. Raw payload storage

The core database stores:

- provenance and document metadata;
- bounded normalized content where appropriate;
- an integrity-checked immutable reference for externally stored payloads.

Large PDF, HTML, binary, or other raw blobs are not stored as core database
fields. Raw payload storage is an infrastructure concern and must preserve
content integrity and provenance.

### 8. Report schema

Phase 7 does not modify the existing Report schema. Existing report builders,
renderers, and exporters remain the output boundary:

```text
Ingestion → Evidence → Research → Existing Reports
```

Any exported report-provenance schema change requires a separate RFC.

## Alternatives Considered

### Event bus first

Rejected for Phase 7. A broker adds delivery, ordering, deployment, and
observability concerns without removing the need for transactions,
idempotency, and restart recovery.

### Agent-controlled runtime

Rejected. Agents may implement bounded extraction or synthesis ports, but
cannot own scheduler, checkpoint, lease, retry, or lifecycle transitions.

### Vector database as the primary store

Rejected. A vector database does not provide the required relational
constraints, transactional checkpoint movement, uniqueness, or authoritative
provenance. A vector index may be a later derived projection.

### New top-level `src/signals`

Rejected. The canonical Signal already exists in `src/core/signals`. A second
package would blur domain, ingestion, extraction, and promotion boundaries.

### ResearchRequest first

Rejected for the MVP. The current requirements describe typed executable work,
not an independent business aggregate with its own long-lived lifecycle. A
future RFC may introduce ResearchRequest if review, assignment, SLA, or
cross-workflow requirements emerge.

### PostgreSQL immediately

Not selected for the MVP. It provides stronger concurrency but adds local,
test, and CI service complexity before workload evidence requires it. The
repository boundary and logical schema preserve a migration path.

### Event-first, Evidence-later

Rejected because it permits ungrounded canonical Signals and conflicts with the
existing Evidence-first research chain.

## Trade-offs

- **Gained:** a bounded Phase 7 scope, explicit external-source isolation,
  deterministic and testable control flow, offline connector validation,
  preservation of Evidence-first semantics, and a clear durability path.
- **Gave up:** immediate distributed processing, live SEC integration in
  Phase 7.1, early PostgreSQL concurrency, a first-class ResearchRequest
  lifecycle, and immediate Evidence/report schema expansion.

## Consequences

### Positive

- Phase 7.1 can begin with ingestion contracts, application models,
  deterministic fixtures, cursor semantics, and deduplication without database
  or domain-model changes.
- Phase 7.2 has an explicit SQLite and repository direction.
- Provider-specific code remains outside core and research.
- Existing Evidence, Signal, Research, Thesis, and Report semantics remain
  intact.
- The project avoids premature distributed infrastructure and agent
  control-plane complexity.

### Negative

- SQLite may need migration when write concurrency or deployment topology
  exceeds the MVP boundary.
- The Evidence revision schema remains unresolved and requires separate
  governance before implementation.
- Report provenance remains limited by the existing Report schema.
- A deterministic fixture proves connector behavior but is not a substitute
  for later live-provider integration.
- Typed WorkItem payload evolution requires explicit schema versioning.

## Governance and Version Impact

This ADR freezes architecture decisions only.

It introduces:

- no code change;
- no schema migration;
- no current runtime behavior change;
- no modification to the core domain;
- no SPEC_VERSION bump by itself.

Future implementation schemas and document changes require their own version
assessment under `SPEC_VERSION.md` and `SCHEMA_EVOLUTION.md`.

## References

- [RFC-001: Durable Ingestion and Research Triggering](../RFC/RFC-001-durable-ingestion-research-triggering.md)
- [Architecture Principles](../docs/00_ARCHITECTURE_PRINCIPLES.md)
- [Object Model](../docs/01_OBJECT_MODEL.md)
- [Workflow Model](../docs/02_WORKFLOW_MODEL.md)
- [Runtime Model](../docs/03_RUNTIME_MODEL.md)
- [Governance](../GOVERNANCE.md)
- [Specification Versioning](../SPEC_VERSION.md)
- [Schema Evolution](../SCHEMA_EVOLUTION.md)
